from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.schemas import RefundApplicationResponse, RefundEligibilityResponse, error_responses
from app.biz.orders import OrderError
from app.biz.refunds import RefundError, apply_refund, check_refund_eligibility, get_refund

router = APIRouter(prefix="/api/v1/refunds", tags=["refunds"])


class EligibilityRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)


class ApplyRefundRequest(EligibilityRequest):
    reason: str = Field(min_length=1, max_length=1000)
    confirmed: bool
    idempotency_key: str = Field(min_length=8, max_length=128)


def _error_response(exc: OrderError | RefundError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "error_code": exc.error_code},
    )


@router.post(
    "/check-eligibility",
    response_model=RefundEligibilityResponse,
    responses=error_responses(404, 503),
)
async def check_eligibility(request: EligibilityRequest):
    try:
        result = await run_in_threadpool(check_refund_eligibility, request.order_id, request.user_id)
    except (OrderError, RefundError) as exc:
        return _error_response(exc)
    return {"eligible": result.eligible, "reason": result.reason, "deadline": result.deadline}


@router.post("/apply", response_model=RefundApplicationResponse, responses=error_responses(404, 409, 503))
async def create_refund(request: ApplyRefundRequest):
    try:
        result = await run_in_threadpool(
            apply_refund,
            request.order_id,
            request.user_id,
            request.reason,
            request.idempotency_key,
            confirmed=request.confirmed,
        )
    except (OrderError, RefundError) as exc:
        return _error_response(exc)
    return _serialize_refund(result)


@router.get("/{refund_id}", response_model=RefundApplicationResponse, responses=error_responses(404, 503))
async def query_refund(refund_id: str, user_id: str = Query(min_length=1, max_length=64)):
    try:
        result = await run_in_threadpool(get_refund, refund_id, user_id)
    except (OrderError, RefundError) as exc:
        return _error_response(exc)
    return _serialize_refund(result)


def _serialize_refund(result) -> dict:
    return {
        "refund_id": result.refund_id,
        "order_id": result.order_id,
        "status": result.status,
        "reason": result.reason,
        "created_at": result.created_at,
    }
