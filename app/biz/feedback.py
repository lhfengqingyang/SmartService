from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.connection import get_engine


@dataclass(frozen=True)
class FeedbackError(RuntimeError):
    error_code: str
    status_code: int


def save_rag_request(
    request_id: UUID,
    tenant_id: str,
    user_id: str,
    scores: list[float],
    experiment: str | None,
    variant: str | None,
    effective_min_score: float,
) -> None:
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ai.rag_requests "
                    "(id, tenant_id, user_id, retrieved_count, top1_score, "
                    "experiment, variant, effective_min_score) "
                    "VALUES (:id, :tenant_id, :user_id, :retrieved_count, :top1_score, "
                    ":experiment, :variant, :effective_min_score)"
                ),
                {
                    "id": request_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "retrieved_count": len(scores),
                    "top1_score": scores[0] if scores else None,
                    "experiment": experiment,
                    "variant": variant,
                    "effective_min_score": effective_min_score,
                },
            )
    except SQLAlchemyError as exc:
        raise FeedbackError("FEEDBACK_STORE_UNAVAILABLE", 503) from exc


def submit_rag_feedback(
    request_id: UUID,
    tenant_id: str,
    user_id: str,
    rating: str,
    question: str | None,
    comment: str | None,
) -> None:
    try:
        with get_engine().begin() as connection:
            owner = connection.execute(
                text("SELECT 1 FROM ai.rag_requests WHERE id=:id AND tenant_id=:tenant AND user_id=:user_id"),
                {"id": request_id, "tenant": tenant_id, "user_id": user_id},
            ).scalar_one_or_none()
            if owner is None:
                raise FeedbackError("REQUEST_NOT_FOUND", 404)
            connection.execute(
                text(
                    "INSERT INTO ai.rag_feedback (request_id, rating, question, comment) "
                    "VALUES (:id, :rating, :question, :comment) "
                    "ON CONFLICT (request_id) DO UPDATE SET "
                    "rating=EXCLUDED.rating, question=EXCLUDED.question, "
                    "comment=EXCLUDED.comment, created_at=now()"
                ),
                {"id": request_id, "rating": rating, "question": question, "comment": comment},
            )
    except SQLAlchemyError as exc:
        raise FeedbackError("FEEDBACK_STORE_UNAVAILABLE", 503) from exc
