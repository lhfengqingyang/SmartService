from datetime import UTC, datetime
from decimal import Decimal

from app.ai.tools import OrderQueryTool, RefundEligibilityTool, RefundPreparationTool
from app.biz.orders import Order, OrderError, OrderItem
from app.biz.refunds import RefundEligibility


def sample_order() -> Order:
    now = datetime(2026, 10, 23, tzinfo=UTC)
    return Order(
        order_id="order-1",
        user_id="trusted-user",
        status="completed",
        total_amount=Decimal("199.00"),
        created_at=now,
        delivered_at=now,
        items=(OrderItem("Headphones", 1, Decimal("199.00")),),
    )


def test_order_tool_binds_user_identity_and_returns_business_result() -> None:
    calls = []

    def query(order_id: str, user_id: str) -> Order:
        calls.append((order_id, user_id))
        return sample_order()

    result = OrderQueryTool("trusted-user", query=query)(order_id="order-1")

    assert calls == [("order-1", "trusted-user")]
    assert result["ok"] is True
    assert result["order"]["total_amount"] == "199.00"
    assert set(OrderQueryTool("trusted-user", query=query).inputs) == {"order_id"}


def test_order_tool_returns_structured_business_error() -> None:
    def query(order_id: str, user_id: str) -> Order:
        raise OrderError("ORDER_NOT_FOUND", "order was not found", 404)

    result = OrderQueryTool("trusted-user", query=query)(order_id="missing")

    assert result == {"ok": False, "error_code": "ORDER_NOT_FOUND", "message": "order was not found"}


def test_refund_eligibility_tool_binds_user_identity() -> None:
    calls = []
    deadline = datetime(2026, 10, 28, tzinfo=UTC)

    def check(order_id: str, user_id: str) -> RefundEligibility:
        calls.append((order_id, user_id))
        return RefundEligibility(True, "within window", deadline)

    result = RefundEligibilityTool("trusted-user", check=check)(order_id="order-1")

    assert calls == [("order-1", "trusted-user")]
    assert result["eligibility"] == {
        "eligible": True,
        "reason": "within window",
        "deadline": "2026-10-28T00:00:00+00:00",
    }


def test_refund_preparation_is_read_only_and_requires_later_confirmation() -> None:
    calls = []

    def check(order_id: str, user_id: str) -> RefundEligibility:
        calls.append((order_id, user_id))
        return RefundEligibility(True, "within window", None)

    result = RefundPreparationTool("trusted-user", check=check)(
        order_id="order-1",
        reason="damaged",
    )

    assert calls == [("order-1", "trusted-user")]
    assert result == {
        "ok": True,
        "pending_action": {
            "action": "apply_refund",
            "order_id": "order-1",
            "reason": "damaged",
        },
        "message": "explicit user confirmation is required before creation",
    }
