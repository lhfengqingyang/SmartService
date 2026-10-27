import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.biz.orders import Order, get_order, validate_identifier
from app.db.connection import get_engine

REFUND_WINDOW = timedelta(days=7)
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")


class RefundError(RuntimeError):
    def __init__(self, error_code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


@dataclass(frozen=True)
class RefundEligibility:
    eligible: bool
    reason: str
    deadline: datetime | None


@dataclass(frozen=True)
class RefundApplication:
    refund_id: str
    order_id: str
    user_id: str
    status: str
    reason: str
    idempotency_key: str
    created_at: datetime


def evaluate_refund_eligibility(order: Order, *, now: datetime | None = None) -> RefundEligibility:
    now = now or datetime.now(UTC)
    if order.status != "completed" or order.delivered_at is None:
        return RefundEligibility(False, "order has not been delivered", None)
    deadline = order.delivered_at + REFUND_WINDOW
    if now > deadline:
        return RefundEligibility(False, "refund window has expired", deadline)
    return RefundEligibility(True, "order is within the seven-day refund window", deadline)


def check_refund_eligibility(
    order_id: str,
    user_id: str,
    *,
    engine: Engine | None = None,
    now: datetime | None = None,
) -> RefundEligibility:
    return evaluate_refund_eligibility(get_order(order_id, user_id, engine=engine), now=now)


def apply_refund(
    order_id: str,
    user_id: str,
    reason: str,
    idempotency_key: str,
    *,
    confirmed: bool,
    engine: Engine | None = None,
    now: datetime | None = None,
) -> RefundApplication:
    if not confirmed:
        raise RefundError("NOT_CONFIRMED", "explicit confirmation is required", 409)
    validate_identifier(order_id, "order_id")
    validate_identifier(user_id, "user_id")
    reason = reason.strip()
    if not 1 <= len(reason) <= 1000:
        raise RefundError("INVALID_REQUEST", "reason must contain 1 to 1000 characters", 422)
    if not _IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise RefundError("INVALID_REQUEST", "idempotency_key is invalid", 422)

    engine = engine or get_engine()
    order = get_order(order_id, user_id, engine=engine)
    eligibility = evaluate_refund_eligibility(order, now=now)
    if not eligibility.eligible:
        raise RefundError("NOT_ELIGIBLE", eligibility.reason, 409)

    try:
        with engine.begin() as connection:
            existing = _find_by_idempotency_key(connection, user_id, idempotency_key)
            if existing is not None:
                if existing["order_id"] != order_id or existing["reason"] != reason:
                    raise RefundError("IDEMPOTENCY_CONFLICT", "idempotency key was reused", 409)
                return _to_application(existing)

            row = connection.execute(
                text(
                    """
                    INSERT INTO biz.refund_applications (
                        order_id, user_id, status, reason, idempotency_key
                    ) VALUES (
                        :order_id, :user_id, 'pending', :reason, :idempotency_key
                    )
                    RETURNING id, order_id, user_id, status, reason, idempotency_key, created_at
                    """
                ),
                {
                    "order_id": order_id,
                    "user_id": user_id,
                    "reason": reason,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().one()
            return _to_application(row)
    except RefundError:
        raise
    except IntegrityError as exc:
        existing = _load_after_conflict(engine, user_id, order_id, idempotency_key)
        if existing is not None and existing.idempotency_key == idempotency_key and existing.reason == reason:
            return existing
        raise RefundError("DUPLICATE_REFUND", "a refund application already exists", 409) from exc
    except SQLAlchemyError as exc:
        raise RefundError("DATABASE_UNAVAILABLE", "failed to create refund application", 503) from exc


def get_refund(refund_id: str, user_id: str, *, engine: Engine | None = None) -> RefundApplication:
    validate_identifier(user_id, "user_id")
    engine = engine or get_engine()
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id, order_id, user_id, status, reason, idempotency_key, created_at
                    FROM biz.refund_applications
                    WHERE id = CAST(:refund_id AS uuid) AND user_id = :user_id
                    """
                ),
                {"refund_id": refund_id, "user_id": user_id},
            ).mappings().one_or_none()
    except SQLAlchemyError as exc:
        raise RefundError("REFUND_NOT_FOUND", "refund application was not found", 404) from exc
    if row is None:
        raise RefundError("REFUND_NOT_FOUND", "refund application was not found", 404)
    return _to_application(row)


def _find_by_idempotency_key(connection, user_id: str, idempotency_key: str):
    return connection.execute(
        text(
            """
            SELECT id, order_id, user_id, status, reason, idempotency_key, created_at
            FROM biz.refund_applications
            WHERE user_id = :user_id AND idempotency_key = :idempotency_key
            """
        ),
        {"user_id": user_id, "idempotency_key": idempotency_key},
    ).mappings().one_or_none()


def _load_after_conflict(
    engine: Engine,
    user_id: str,
    order_id: str,
    idempotency_key: str,
) -> RefundApplication | None:
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id, order_id, user_id, status, reason, idempotency_key, created_at
                    FROM biz.refund_applications
                    WHERE (user_id = :user_id AND idempotency_key = :idempotency_key)
                       OR order_id = :order_id
                    LIMIT 1
                    """
                ),
                {"user_id": user_id, "order_id": order_id, "idempotency_key": idempotency_key},
            ).mappings().one_or_none()
    except SQLAlchemyError:
        return None
    return _to_application(row) if row is not None else None


def _to_application(row) -> RefundApplication:
    return RefundApplication(
        refund_id=str(row["id"]),
        order_id=row["order_id"],
        user_id=row["user_id"],
        status=row["status"],
        reason=row["reason"],
        idempotency_key=row["idempotency_key"],
        created_at=row["created_at"],
    )
