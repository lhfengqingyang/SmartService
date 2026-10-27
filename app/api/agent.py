import ast
import asyncio
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.ai.agent import (
    AgentAnswer,
    CustomerServiceAgentError,
    answer_business_question,
    verify_grounded_refund,
)
from app.ai.conversations import (
    ConversationNotFoundError,
    PendingRefund,
    conversation_store,
)
from app.ai.rag import RequesterContext
from app.api.schemas import AgentChatResponse, error_responses
from app.biz.orders import OrderError
from app.biz.refunds import RefundError, apply_refund

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(min_length=1, max_length=64)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    roles: list[str] = Field(default_factory=list, max_length=20)
    task_mode: Literal["standard", "refund_policy"] = "standard"
    conversation_id: UUID | None = None
    confirm_pending_action: bool = False
    cancel_pending_action: bool = False


AGENT_TOTAL_TIMEOUT_SECONDS = 45.0


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    response_model_exclude_unset=True,
    responses=error_responses(404, 409, 502, 503, 504),
)
async def agent_chat(request: AgentChatRequest):
    try:
        if request.confirm_pending_action and request.cancel_pending_action:
            raise ValueError("confirm_pending_action and cancel_pending_action cannot both be true")
        conversation = conversation_store.get_or_create(
            request.user_id,
            str(request.conversation_id) if request.conversation_id else None,
        )
        if request.task_mode == "refund_policy":
            if not request.tenant_id:
                raise ValueError("tenant_id is required for refund_policy task")
            conversation_store.set_task_context(conversation.conversation_id, request.tenant_id, None)
        if request.confirm_pending_action:
            return await _confirm_pending_refund(conversation)
        if request.cancel_pending_action:
            return _cancel_pending_refund(conversation)

        if request.task_mode == "refund_policy":
            result = await asyncio.wait_for(
                run_in_threadpool(
                    answer_business_question,
                    request.message,
                    request.user_id,
                    requester=RequesterContext(
                        request.tenant_id,
                        request.user_id,
                        tuple(dict.fromkeys(request.roles)),
                    ),
                    last_order_id=conversation.last_order_id,
                ),
                timeout=AGENT_TOTAL_TIMEOUT_SECONDS,
            )
            order_call = next((call for call in result.tool_calls if call.tool_name == "order_query"), None)
            if order_call:
                conversation_store.set_task_context(
                    conversation.conversation_id, request.tenant_id, order_call.arguments.get("order_id")
                )
            verified, safe_answer = verify_grounded_refund(result)
            if not verified:
                conversation_store.set_pending_refund(conversation.conversation_id, None)
                return {
                    "answer": safe_answer,
                    "tool_calls": [
                        {"tool_name": call.tool_name, "arguments": call.arguments, "result": call.result}
                        for call in result.tool_calls
                    ],
                    "conversation_id": conversation.conversation_id,
                    "pending_action": None,
                }
        else:
            result = await asyncio.wait_for(
                run_in_threadpool(answer_business_question, request.message, request.user_id),
                timeout=AGENT_TOTAL_TIMEOUT_SECONDS,
            )
        pending = _pending_refund_from_answer(result)
        if pending is not None:
            conversation_store.set_pending_refund(conversation.conversation_id, pending)
            conversation.pending_refund = pending
    except TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"detail": "agent execution timed out", "error_code": "AGENT_TIMEOUT"},
        )
    except ConversationNotFoundError as exc:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc), "error_code": "CONVERSATION_NOT_FOUND"},
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc), "error_code": "INVALID_REQUEST"},
        )
    except CustomerServiceAgentError as exc:
        return JSONResponse(
            status_code=502,
            content={"detail": str(exc), "error_code": "AGENT_UNAVAILABLE"},
        )
    answer = result.answer
    if pending is not None:
        answer = (
            f"订单 {pending.order_id} 的模拟退款申请已准备好，尚未创建。"
            "请在应用中使用确认操作；客户端须携带当前 conversation_id "
            "并提交 confirm_pending_action=true。仅回复“确认”不会创建申请。"
        )
    return {
        "answer": answer,
        "tool_calls": [
            {
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result": call.result,
            }
            for call in result.tool_calls
        ],
        "conversation_id": conversation.conversation_id,
        "pending_action": _serialize_pending(conversation.pending_refund),
    }


def _pending_refund_from_answer(result: AgentAnswer) -> PendingRefund | None:
    for call in reversed(result.tool_calls):
        if call.tool_name != "refund_prepare":
            continue
        tool_result = call.result
        if isinstance(tool_result, str):
            try:
                tool_result = json.loads(tool_result)
            except json.JSONDecodeError:
                try:
                    tool_result = ast.literal_eval(tool_result)
                except (SyntaxError, ValueError):
                    continue
        if not isinstance(tool_result, dict):
            continue
        action = tool_result.get("pending_action")
        if tool_result.get("ok") is True and isinstance(action, dict):
            order_id = action.get("order_id")
            reason = action.get("reason")
            if isinstance(order_id, str) and isinstance(reason, str):
                return PendingRefund(uuid4().hex, order_id, reason)
    return None


async def _confirm_pending_refund(conversation):
    pending = conversation.pending_refund
    if pending is None:
        return JSONResponse(
            status_code=409,
            content={"detail": "no action is awaiting confirmation", "error_code": "NO_PENDING_ACTION"},
        )
    try:
        application = await run_in_threadpool(
            apply_refund,
            pending.order_id,
            conversation.user_id,
            pending.reason,
            f"agent:{conversation.conversation_id}:{pending.action_id}",
            confirmed=True,
        )
    except (OrderError, RefundError) as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc), "error_code": exc.error_code},
        )
    conversation_store.set_pending_refund(conversation.conversation_id, None)
    return {
        "answer": "模拟退款申请已创建，当前状态为 pending；这不代表真实资金已经退回。",
        "tool_calls": [],
        "conversation_id": conversation.conversation_id,
        "pending_action": None,
        "refund_application": {
            "refund_id": application.refund_id,
            "order_id": application.order_id,
            "status": application.status,
            "reason": application.reason,
            "created_at": application.created_at,
        },
    }


def _serialize_pending(pending: PendingRefund | None) -> dict | None:
    if pending is None:
        return None
    return {
        "action_id": pending.action_id,
        "action": "apply_refund",
        "order_id": pending.order_id,
        "reason": pending.reason,
        "requires_confirmation": True,
    }


def _cancel_pending_refund(conversation):
    if conversation.pending_refund is None:
        return JSONResponse(
            status_code=409,
            content={"detail": "no action is awaiting confirmation", "error_code": "NO_PENDING_ACTION"},
        )
    conversation_store.set_pending_refund(conversation.conversation_id, None)
    return {
        "answer": "已取消待确认的模拟退款申请。",
        "tool_calls": [],
        "conversation_id": conversation.conversation_id,
        "pending_action": None,
    }
