"""Gate a fixed evaluation report on availability, structural checks and human fact review."""

import argparse
import json
from pathlib import Path
from typing import Any

CRITICAL_CHECKS = frozenset(
    {
        "source_recall_at_k",
        "chunk_recall_at_k",
        "valid_citation",
        "no_evidence",
        "required_tools_present",
        "no_unexpected_prepare",
        "tool_arguments",
        "pending_action",
        "pending_order_id",
    }
)


def evaluate_gate(
    report: dict[str, Any],
    review: dict[str, Any],
    *,
    minimum_availability: float = 0.95,
    minimum_tool_selection: float = 0.90,
    comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    rows = report["cases"]
    fingerprint = report.get("case_fingerprint")
    if not fingerprint or review.get("case_fingerprint") != fingerprint:
        reasons.append("review fingerprint does not match the fixed cases")
    data_fingerprint = report.get("data_fingerprint")
    if not data_fingerprint or review.get("data_fingerprint") != data_fingerprint:
        reasons.append("review fingerprint does not match the demo data snapshot")

    reviews = review.get("reviews", [])
    review_ids = [row.get("id") for row in reviews if isinstance(row, dict)]
    case_ids = [row["id"] for row in rows]
    if len(review_ids) != len(set(review_ids)) or set(review_ids) != set(case_ids):
        reasons.append("every case needs exactly one human review")
    by_id = {row["id"]: row for row in reviews if isinstance(row, dict) and isinstance(row.get("id"), str)}

    total = len(rows)
    available = sum(row["availability"] == "ok" for row in rows)
    availability = available / total if total else 0.0
    if not total or availability < minimum_availability:
        reasons.append(f"availability {available}/{total} below {minimum_availability:.0%}")

    for row in rows:
        case_id = row["id"]
        if row["availability"] != "ok":
            continue
        for check, passed in row["checks"].items():
            if check in CRITICAL_CHECKS and passed is not True:
                reasons.append(f"{case_id}: critical check {check} failed")
        human = by_id.get(case_id, {})
        if human.get("fact_supported") is not True:
            reasons.append(f"{case_id}: facts not approved by human review")
        if human.get("safe") is not True:
            reasons.append(f"{case_id}: safety not approved by human review")
        if not isinstance(human.get("note"), str) or not human["note"].strip():
            reasons.append(f"{case_id}: human review note is required")

    tool_selection = report.get("metrics", {}).get("tool_selection")
    if tool_selection and tool_selection["rate"] < minimum_tool_selection:
        reasons.append(
            f"tool selection {tool_selection['passed']}/{tool_selection['total']} below {minimum_tool_selection:.0%}"
        )

    if comparison is not None:
        if comparison.get("case_count") != total or comparison.get("case_content_verified") is not True:
            reasons.append("comparison does not match verified fixed cases")
        if comparison.get("data_content_verified") is not True:
            reasons.append("comparison does not match verified demo data snapshots")
        if comparison.get("automated_signal") in {"regressed", "insufficient_paired_cases"}:
            reasons.append(f"comparison signal: {comparison['automated_signal']}")

    return {
        "decision": "pass" if not reasons else "block",
        "case_count": total,
        "available": available,
        "reasons": reasons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Block a release when fixed evals or human review fail")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    review = json.loads(args.review.read_text(encoding="utf-8"))
    comparison = json.loads(args.comparison.read_text(encoding="utf-8")) if args.comparison else None
    decision = evaluate_gate(report, review, comparison=comparison)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    if decision["decision"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
