from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import refunds
from app.biz.orders import Order
from app.biz.refunds import (
    RefundApplication,
    RefundError,
    evaluate_refund_eligibility,
)
from app.main import app

client = TestClient(app)


def make_order(*, status: str = "completed", delivered_days_ago: int | None = 2) -> Order:
    now = datetime(2026, 10, 23, tzinfo=UTC)
    delivered_at = None if delivered_days_ago is None else now - timedelta(days=delivered_days_ago)
    return Order(
        order_id="order-1",
        user_id="user-1",
        status=status,
        total_amount=Decimal("99.00"),
        created_at=now - timedelta(days=10),
        delivered_at=delivered_at,
        items=(),
    )


def test_refund_eligibility_uses_delivery_time_and_seven_day_window() -> None:
    now = datetime(2026, 10, 23, tzinfo=UTC)

    eligible = evaluate_refund_eligibility(make_order(delivered_days_ago=2), now=now)
    expired = evaluate_refund_eligibility(make_order(delivered_days_ago=8), now=now)
    undelivered = evaluate_refund_eligibility(make_order(status="shipped", delivered_days_ago=None), now=now)

    assert eligible.eligible is True
    assert eligible.deadline == datetime(2026, 10, 28, tzinfo=UTC)
    assert expired.eligible is False
    assert expired.reason == "refund window has expired"
    assert undelivered.eligible is False
    assert undelivered.deadline is None


def test_refund_apply_requires_explicit_confirmation(monkeypatch) -> None:
    def not_confirmed(*args, **kwargs):
        raise RefundError("NOT_CONFIRMED", "explicit confirmation is required", 409)

    monkeypatch.setattr(refunds, "apply_refund", not_confirmed)
    response = client.post(
        "/api/v1/refunds/apply",
        json={
            "order_id": "order-1",
            "user_id": "user-1",
            "reason": "No longer needed",
            "confirmed": False,
            "idempotency_key": "request-0001",
        },
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "NOT_CONFIRMED"


def test_refund_apply_returns_simulated_pending_application(monkeypatch) -> None:
    created_at = datetime(2026, 10, 23, tzinfo=UTC)
    application = RefundApplication(
        refund_id="00000000-0000-0000-0000-000000000001",
        order_id="order-1",
        user_id="user-1",
        status="pending",
        reason="No longer needed",
        idempotency_key="request-0001",
        created_at=created_at,
    )
    monkeypatch.setattr(refunds, "apply_refund", lambda *args, **kwargs: application)

    response = client.post(
        "/api/v1/refunds/apply",
        json={
            "order_id": "order-1",
            "user_id": "user-1",
            "reason": "No longer needed",
            "confirmed": True,
            "idempotency_key": "request-0001",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert "idempotency_key" not in response.json()


def test_invalid_idempotency_key_is_rejected_before_database() -> None:
    from app.biz.refunds import apply_refund

    with pytest.raises(RefundError) as exc_info:
        apply_refund("order-1", "user-1", "reason", "short", confirmed=True)

    assert exc_info.value.error_code == "INVALID_REQUEST"
