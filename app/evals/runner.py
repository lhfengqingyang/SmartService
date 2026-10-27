import argparse
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_embedding_settings
from app.db.connection import get_engine
from app.main import app

DEFAULT_CASES = Path(__file__).resolve().parents[2] / "evals" / "cases" / "smartservice.jsonl"
_CITATION = re.compile(r"\[(\d+)\]")


def demo_data_fingerprint() -> str:
    """Fingerprint the fixture knowledge and orders used by live evaluation."""
    queries = (
        "SELECT filename, content_sha256, tenant_id, owner_user_id, visibility, allowed_roles "
        "FROM ai.documents WHERE tenant_id = 'demo' ORDER BY filename, content_sha256",
        "SELECT d.filename, c.chunk_index, c.heading, c.chunk_text, c.content_sha256 "
        "FROM ai.document_chunks c JOIN ai.documents d ON d.id = c.document_id "
        "WHERE d.tenant_id = 'demo' ORDER BY d.filename, c.chunk_index, c.content_sha256",
        "SELECT id, user_id, status, total_amount, created_at, delivered_at "
        "FROM biz.orders WHERE id LIKE 'demo-%' ORDER BY id",
        "SELECT order_id, product_name, quantity, price FROM biz.order_items "
        "WHERE order_id LIKE 'demo-%' ORDER BY order_id, product_name",
    )
    with get_engine().connect() as connection:
        snapshot = [
            [dict(row) for row in connection.execute(text(query)).mappings()]
            for query in queries
        ]
    embedding = get_embedding_settings()
    payload = {"tables": snapshot, "embedding_model": embedding.model, "embedding_dimensions": embedding.dimensions}
    encoded = json.dumps(payload, default=str, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError(f"{path}:{line_number}: each row needs a string id")
            rows.append(row)
    identifiers = [row["id"] for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{path}: duplicate case ids")
    return rows


def collect_live(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required_documents = {
        filename
        for case in cases
        if case["kind"] == "rag"
        for filename in case.get("expected_filenames", [])
    }
    if required_documents:
        with get_engine().connect() as connection:
            available_documents = set(
                connection.execute(
                    text(
                        "SELECT filename FROM ai.documents "
                        "WHERE tenant_id = 'demo' AND owner_user_id = 'demo-user'"
                    )
                ).scalars()
            )
        missing_documents = required_documents - available_documents
        if missing_documents:
            raise ValueError(
                "upload the fixture documents before live RAG evaluation: "
                + ", ".join(sorted(missing_documents))
            )
    data_fingerprint = demo_data_fingerprint()
    client = TestClient(app)
    observations = []
    for case in cases:
        route = "/api/v1/chat" if case["kind"] == "rag" else "/api/v1/agent/chat"
        started = time.perf_counter()
        try:
            response = client.post(route, json=case["request"])
            observations.append(
                {
                    "id": case["id"],
                    "status_code": response.status_code,
                    "response": response.json(),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "data_fingerprint": data_fingerprint,
                }
            )
        except Exception as exc:
            observations.append(
                {
                    "id": case["id"],
                    "status_code": 0,
                    "response": {"error_code": type(exc).__name__},
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "data_fingerprint": data_fingerprint,
                }
            )
    if demo_data_fingerprint() != data_fingerprint:
        raise ValueError("demo data changed during live evaluation")
    return observations


def score_case(case: dict[str, Any], observation: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {"id": case["id"], "kind": case["kind"], "checks": {}}
    if observation is None:
        result["availability"] = "missing"
        return result
    status_code = observation.get("status_code")
    response = observation.get("response")
    if not isinstance(response, dict):
        raise ValueError(f"{case['id']}: observation response must be an object")
    result["latency_ms"] = observation.get("latency_ms")
    if status_code != 200:
        result["availability"] = "error"
        result["error_code"] = response.get("error_code", f"HTTP_{status_code}")
        return result

    result["availability"] = "ok"
    checks = result["checks"]
    if case["kind"] == "rag":
        sources = response.get("sources")
        if not isinstance(sources, list):
            raise ValueError(f"{case['id']}: RAG observation needs sources")
        filenames = {item.get("filename") for item in sources if isinstance(item, dict)}
        answer = response.get("answer", "")
        if not isinstance(answer, str):
            raise ValueError(f"{case['id']}: RAG answer must be text")
        if case["answerable"]:
            expected = set(case["expected_filenames"])
            checks["source_recall_at_k"] = bool(expected & filenames)
            if "expected_chunks" in case:
                returned_chunks = {
                    (item.get("filename"), item.get("chunk_index"))
                    for item in sources
                    if isinstance(item, dict)
                }
                required_chunks = {
                    (item["filename"], item["chunk_index"])
                    for item in case["expected_chunks"]
                }
                checks["chunk_recall_at_k"] = bool(required_chunks & returned_chunks)
            citations = {int(match) for match in _CITATION.findall(answer)}
            checks["valid_citation"] = bool(citations) and all(
                1 <= citation <= len(sources) for citation in citations
            )
        else:
            checks["no_evidence"] = sources == [] and answer == "现有知识库无法确认这个问题。"
        result["manual_review"] = case.get("review_notes", "")
    elif case["kind"] == "agent":
        calls = response.get("tool_calls")
        if not isinstance(calls, list):
            raise ValueError(f"{case['id']}: Agent observation needs tool_calls")
        names = [call.get("tool_name") for call in calls if isinstance(call, dict)]
        checks["tool_selection"] = sorted(names) == sorted(case["expected_tools"])
        actual_tools = Counter(names)
        required_tools = Counter(case["expected_tools"])
        checks["required_tools_present"] = all(actual_tools[name] >= count for name, count in required_tools.items())
        checks["no_unexpected_prepare"] = actual_tools["refund_prepare"] <= required_tools["refund_prepare"]
        read_calls = [
            (call.get("tool_name"), call.get("arguments", {}).get("order_id"))
            for call in calls
            if isinstance(call, dict)
            and call.get("tool_name") in {"order_query", "refund_eligibility_check"}
            and isinstance(call.get("arguments"), dict)
        ]
        checks["no_duplicate_read"] = len(read_calls) == len(set(read_calls))
        expected_order_id = case.get("expected_order_id")
        checks["tool_arguments"] = (bool(calls) or not case["expected_tools"]) and all(
            isinstance(call, dict)
            and isinstance(call.get("arguments"), dict)
            and call["arguments"].get("order_id") == expected_order_id
            for call in calls
        )
        checks["pending_action"] = bool(response.get("pending_action")) == case["expected_pending"]
        if case["expected_pending"]:
            action = response.get("pending_action")
            checks["pending_order_id"] = (
                isinstance(action, dict) and action.get("order_id") == expected_order_id
            )
        result["manual_review"] = case.get("review_notes", "")
    else:
        raise ValueError(f"{case['id']}: unknown kind")
    return result


def build_report(
    cases: list[dict[str, Any]], observations: list[dict[str, Any]]
) -> dict[str, Any]:
    case_ids = {case["id"] for case in cases}
    observation_ids = [item["id"] for item in observations]
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("duplicate observation ids")
    unknown = set(observation_ids) - case_ids
    if unknown:
        raise ValueError(f"unknown observation ids: {sorted(unknown)}")
    data_fingerprints = {item.get("data_fingerprint") for item in observations}
    if len(data_fingerprints) > 1:
        raise ValueError("observations have different demo data fingerprints")
    by_id = {item["id"]: item for item in observations}
    results = [score_case(case, by_id.get(case["id"])) for case in cases]
    check_totals: Counter[str] = Counter()
    check_passed: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    for result in results:
        if result["availability"] == "error":
            errors[result["error_code"]] += 1
        for name, passed in result["checks"].items():
            check_totals[name] += 1
            check_passed[name] += int(passed)
    return {
        "data_fingerprint": next(iter(data_fingerprints)) if data_fingerprints else None,
        "case_fingerprint": hashlib.sha256(
            json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "case_count": len(cases),
        "observed": sum(item["availability"] != "missing" for item in results),
        "available": sum(item["availability"] == "ok" for item in results),
        "errors": dict(errors),
        "metrics": {
            name: {
                "passed": check_passed[name],
                "total": count,
                "rate": round(check_passed[name] / count, 4),
            }
            for name, count in sorted(check_totals.items())
        },
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score fixed RAG and Agent evaluation cases")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--kind", choices=("all", "rag", "agent"), default="all")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--observations", type=Path, help="score previously recorded JSONL responses")
    source.add_argument("--live", action="store_true", help="call real DB, Embedding and GLM services")
    parser.add_argument("--observations-out", type=Path, help="save responses collected with --live")
    parser.add_argument("--report", type=Path, required=True, help="write JSON score report")
    args = parser.parse_args()
    cases = load_jsonl(args.cases)
    if args.kind != "all":
        cases = [case for case in cases if case["kind"] == args.kind]
    observations = collect_live(cases) if args.live else load_jsonl(args.observations)
    if args.observations_out:
        if not args.live:
            parser.error("--observations-out requires --live")
        args.observations_out.parent.mkdir(parents=True, exist_ok=True)
        args.observations_out.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in observations),
            encoding="utf-8",
        )
    report = build_report(cases, observations)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_keys = ("case_count", "observed", "available", "errors", "metrics")
    print(
        json.dumps(
            {key: report[key] for key in summary_keys},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
