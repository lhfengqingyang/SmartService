from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.api.schemas import OrderResponse, error_responses
from app.biz.orders import OrderError, get_order

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


@router.get("/{order_id}", response_model=OrderResponse, responses=error_responses(404, 503))
async def query_order(order_id: str, user_id: str = Query(min_length=1, max_length=64)):
    try:
        order = await run_in_threadpool(get_order, order_id, user_id)
    except OrderError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc), "error_code": exc.error_code},
        )
    return {
        "order_id": order.order_id,
        "user_id": order.user_id,
        "status": order.status,
        "items": [
            {
                "product_name": item.product_name,
                "quantity": item.quantity,
                "price": float(item.price),
            }
            for item in order.items
        ],
        "total_amount": float(order.total_amount),
        "created_at": order.created_at,
        "delivered_at": order.delivered_at,
    }
