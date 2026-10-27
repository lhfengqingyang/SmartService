from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api import orders
from app.biz.orders import Order, OrderError, OrderItem
from app.main import app

client = TestClient(app)


def sample_order() -> Order:
    now = datetime.now(UTC)
    return Order(
        order_id="order-1",
        user_id="user-1",
        status="completed",
        total_amount=Decimal("199.00"),
        created_at=now,
        delivered_at=now,
        items=(OrderItem("Headphones", 1, Decimal("199.00")),),
    )


def test_order_endpoint_returns_owned_order(monkeypatch) -> None:
    monkeypatch.setattr(orders, "get_order", lambda order_id, user_id: sample_order())

    response = client.get("/api/v1/orders/order-1", params={"user_id": "user-1"})

    assert response.status_code == 200
    assert response.json()["order_id"] == "order-1"
    assert response.json()["items"] == [{"product_name": "Headphones", "quantity": 1, "price": 199.0}]


def test_order_endpoint_hides_other_users_order(monkeypatch) -> None:
    def not_found(order_id: str, user_id: str) -> Order:
        raise OrderError("ORDER_NOT_FOUND", "order was not found", 404)

    monkeypatch.setattr(orders, "get_order", not_found)
    response = client.get("/api/v1/orders/order-1", params={"user_id": "other-user"})

    assert response.status_code == 404
    assert response.json()["error_code"] == "ORDER_NOT_FOUND"
