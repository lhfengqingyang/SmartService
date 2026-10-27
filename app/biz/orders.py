import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.connection import get_engine

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


class OrderError(RuntimeError):
    def __init__(self, error_code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


@dataclass(frozen=True)
class OrderItem:
    product_name: str
    quantity: int
    price: Decimal


@dataclass(frozen=True)
class Order:
    order_id: str
    user_id: str
    status: str
    total_amount: Decimal
    created_at: datetime
    delivered_at: datetime | None
    items: tuple[OrderItem, ...]


def validate_identifier(value: str, field_name: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise OrderError("INVALID_REQUEST", f"{field_name} is invalid", 422)


def get_order(order_id: str, user_id: str, *, engine: Engine | None = None) -> Order:
    validate_identifier(order_id, "order_id")
    validate_identifier(user_id, "user_id")
    engine = engine or get_engine()
    try:
        with engine.connect() as connection:
            order_row = connection.execute(
                text(
                    """
                    SELECT id, user_id, status, total_amount, created_at, delivered_at
                    FROM biz.orders
                    WHERE id = :order_id AND user_id = :user_id
                    """
                ),
                {"order_id": order_id, "user_id": user_id},
            ).mappings().one_or_none()
            if order_row is None:
                raise OrderError("ORDER_NOT_FOUND", "order was not found", 404)
            item_rows = connection.execute(
                text(
                    """
                    SELECT product_name, quantity, price
                    FROM biz.order_items
                    WHERE order_id = :order_id
                    ORDER BY id
                    """
                ),
                {"order_id": order_id},
            ).mappings().all()
    except OrderError:
        raise
    except SQLAlchemyError as exc:
        raise OrderError("DATABASE_UNAVAILABLE", "failed to query order", 503) from exc

    return Order(
        order_id=order_row["id"],
        user_id=order_row["user_id"],
        status=order_row["status"],
        total_amount=order_row["total_amount"],
        created_at=order_row["created_at"],
        delivered_at=order_row["delivered_at"],
        items=tuple(
            OrderItem(
                product_name=row["product_name"],
                quantity=row["quantity"],
                price=row["price"],
            )
            for row in item_rows
        ),
    )
