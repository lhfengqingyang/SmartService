import argparse
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.db.connection import get_engine
from app.evals.runner import load_jsonl

PRIVATE_ROOT = Path(__file__).resolve().parents[2] / "evals" / "private_cases"
FAILURE_TYPES = {
    "retrieval_missing",
    "retrieval_irrelevant",
    "answer_unsupported",
    "incorrect_refusal",
    "other",
}


def feedback_request_id(case_id: str) -> str:
    if not case_id.startswith("feedback-"):
        raise ValueError(f"{case_id}: invalid feedback case id")
    try:
        return str(UUID(case_id.removeprefix("feedback-")))
    except ValueError as exc:
        raise ValueError(f"{case_id}: invalid feedback case id") from exc


def sync_queue(request_id: UUID | None = None) -> int:
    with get_engine().begin() as connection:
        return connection.execute(
            text(
                "INSERT INTO ai.feedback_review_queue (request_id) "
                "SELECT f.request_id FROM ai.rag_feedback f "
                "WHERE f.rating='unhelpful' AND f.question IS NOT NULL "
                "AND (CAST(:request_id AS uuid) IS NULL OR f.request_id=CAST(:request_id AS uuid)) "
                "ON CONFLICT (request_id) DO NOTHING"
            ),
            {"request_id": str(request_id) if request_id else None},
        ).rowcount


def complete_reviews(rows: list[dict[str, Any]]) -> None:
    decisions = []
    for row in rows:
        approved = row.get("approved") is True
        rejected = row.get("rejected") is True
        if approved and rejected:
            raise ValueError(f"{row.get('id')}: cannot approve and reject together")
        if not approved and not rejected:
            continue
        request_id = feedback_request_id(row["id"])
        decisions.append((request_id, "approved" if approved else "rejected"))
    with get_engine().begin() as connection:
        for request_id, status in decisions:
            connection.execute(
                text(
                    "UPDATE ai.feedback_review_queue SET status=:status, reviewed_at=now() "
                    "WHERE request_id=CAST(:request_id AS uuid) AND status='pending'"
                ),
                {"request_id": request_id, "status": status},
            )


def export_candidates() -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                "SELECT f.request_id, f.question, f.comment, r.tenant_id, r.user_id, "
                "r.experiment, r.variant, r.retrieved_count, r.top1_score "
                "FROM ai.feedback_review_queue q "
                "JOIN ai.rag_feedback f ON f.request_id=q.request_id "
                "JOIN ai.rag_requests r ON r.id=f.request_id "
                "WHERE q.status='pending' AND f.rating='unhelpful' AND f.question IS NOT NULL "
                "ORDER BY f.created_at DESC"
            )
        ).mappings()
        return [
            {
                "id": f"feedback-{row['request_id']}",
                "kind": "rag",
                "request": {
                    "question": row["question"],
                    "tenant_id": row["tenant_id"],
                    "user_id": row["user_id"],
                    "roles": [],
                },
                "feedback_comment": row["comment"],
                "experiment": row["experiment"],
                "variant": row["variant"],
                "retrieved_count": row["retrieved_count"],
                "top1_score": row["top1_score"],
                "approved": False,
                "rejected": False,
                "answerable": None,
                "expected_filenames": [],
                "review_notes": "",
                "failure_type": None,
            }
            for row in rows
        ]


def promote_approved(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    promoted = []
    for row in rows:
        if row.get("approved") is True and row.get("rejected") is True:
            raise ValueError(f"{row.get('id')}: cannot approve and reject together")
        if row.get("approved") is not True:
            continue
        feedback_request_id(row["id"])
        request = row.get("request")
        answerable = row.get("answerable")
        filenames = row.get("expected_filenames")
        notes = row.get("review_notes")
        failure_type = row.get("failure_type")
        if (
            row.get("kind") != "rag"
            or not isinstance(request, dict)
            or not all(
                isinstance(request.get(key), str) and request[key].strip()
                for key in ("question", "tenant_id", "user_id")
            )
            or not isinstance(request.get("roles"), list)
            or not isinstance(answerable, bool)
            or not isinstance(filenames, list)
            or not all(isinstance(name, str) and name.strip() for name in filenames)
            or (answerable and not filenames)
            or (not answerable and filenames)
            or not isinstance(notes, str)
            or not notes.strip()
            or failure_type not in FAILURE_TYPES
        ):
            raise ValueError(f"{row.get('id')}: approved case needs complete human labels")
        promoted.append(
            {
                "id": row["id"],
                "kind": "rag",
                "request": request,
                "answerable": answerable,
                "expected_filenames": filenames,
                "review_notes": notes,
                "failure_type": failure_type,
            }
        )
    return promoted


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Review opted-in negative RAG feedback")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("--out", type=Path, required=True)
    subparsers.add_parser("sync")
    promote = subparsers.add_parser("promote")
    promote.add_argument("--reviewed", type=Path, required=True)
    promote.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "sync":
        print(f"{sync_queue()} feedback items enqueued")
        return
    output = args.out.resolve()
    if not output.is_relative_to(PRIVATE_ROOT):
        parser.error(f"output must be inside {PRIVATE_ROOT}")
    if args.command == "export":
        rows = export_candidates()
    else:
        reviewed = load_jsonl(args.reviewed)
        approved = promote_approved(reviewed)
        for row in reviewed:
            if row.get("rejected") is True:
                feedback_request_id(row["id"])
        existing = load_jsonl(output) if output.exists() else []
        by_id = {row["id"]: row for row in existing}
        by_id.update({row["id"]: row for row in approved})
        rows = list(by_id.values())
    write_jsonl(output, rows)
    if args.command == "promote":
        complete_reviews(reviewed)
    print(f"{len(rows)} cases written to {output}")


if __name__ == "__main__":
    main()
