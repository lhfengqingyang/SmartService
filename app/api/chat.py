import hashlib
from time import perf_counter
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.ai.rag import RequesterContext, RetrievalError, answer_question
from app.api.schemas import ChatResponse, FeedbackResponse, error_responses
from app.biz.feedback import FeedbackError, save_rag_request, submit_rag_feedback
from app.observability import record_rag_request

router = APIRouter(prefix="/api/v1", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    tenant_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    roles: list[str] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    experiment: Literal["threshold_v1"] | None = None


def assign_variant(tenant_id: str, user_id: str) -> str:
    cohort = f"{tenant_id}:{user_id}".encode()
    return "A" if hashlib.sha256(cohort).digest()[0] % 2 == 0 else "B"


class FeedbackRequest(BaseModel):
    request_id: UUID
    tenant_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    rating: Literal["helpful", "unhelpful"]
    question: str | None = Field(default=None, min_length=1, max_length=4000)
    comment: str | None = Field(default=None, max_length=1000)


@router.post("/chat/feedback", response_model=FeedbackResponse, responses=error_responses(404, 503))
async def chat_feedback(request: FeedbackRequest):
    try:
        await run_in_threadpool(
            submit_rag_feedback,
            request.request_id,
            request.tenant_id,
            request.user_id,
            request.rating,
            request.question,
            request.comment,
        )
    except FeedbackError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.error_code, "error_code": exc.error_code},
        )
    return {"saved": True, "request_id": request.request_id}


@router.post("/chat", response_model=ChatResponse, responses=error_responses(502, 503))
async def chat(request: ChatRequest):
    started = perf_counter()
    variant = assign_variant(request.tenant_id, request.user_id) if request.experiment else None
    effective_min_score = (
        min(1.0, request.min_score + 0.1)
        if variant == "B"
        else request.min_score
    )
    status_code = 200
    error_code = None
    sources = ()
    try:
        result = await run_in_threadpool(
            answer_question,
            request.question,
            RequesterContext(
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                roles=tuple(dict.fromkeys(request.roles)),
            ),
            top_k=request.top_k,
            min_score=effective_min_score,
        )
        sources = result.sources
    except ValueError as exc:
        status_code, error_code = 422, "INVALID_REQUEST"
        return JSONResponse(status_code=422, content={"detail": str(exc), "error_code": "INVALID_REQUEST"})
    except RetrievalError as exc:
        status_code = 503 if exc.error_code == "DATABASE_UNAVAILABLE" else 502
        error_code = exc.error_code
        return JSONResponse(
            status_code=status_code,
            content={"detail": str(exc), "error_code": exc.error_code},
        )
    finally:
        record_rag_request(
            status_code=status_code,
            latency_ms=(perf_counter() - started) * 1000,
            sources=sources,
            error_code=error_code,
        )

    request_id = uuid4()
    try:
        await run_in_threadpool(
            save_rag_request,
            request_id,
            request.tenant_id,
            request.user_id,
            [source.score for source in result.sources],
            request.experiment,
            variant,
            effective_min_score,
        )
    except FeedbackError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.error_code, "error_code": exc.error_code},
        )

    return {
        "request_id": request_id,
        "experiment": request.experiment,
        "variant": variant,
        "effective_min_score": effective_min_score,
        "answer": result.answer,
        "sources": [
            {
                "document_id": source.document_id,
                "filename": source.filename,
                "chunk_index": source.chunk_index,
                "heading": source.heading,
                "chunk_text": source.chunk_text,
                "score": source.score,
            }
            for source in result.sources
        ],
        "conversation_id": None,
        "tool_calls": [],
    }

