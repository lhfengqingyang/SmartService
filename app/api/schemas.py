from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    error_code: str


def error_responses(*status_codes: int) -> dict[int, dict]:
    return {status_code: {"model": ErrorResponse} for status_code in status_codes}


class HealthResponse(BaseModel):
    status: Literal["ok"]


class HealthAliveResponse(HealthResponse):
    version: str


class KnowledgeUploadResponse(BaseModel):
    document_id: UUID
    filename: str
    chunk_count: int
    status: Literal["processed"]


class KnowledgeDocumentResponse(BaseModel):
    document_id: UUID
    filename: str
    chunk_count: int
    visibility: Literal["private", "tenant", "public"]
    created_at: datetime


class KnowledgeDocumentPageResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]
    total: int
    page: int
    page_size: int


class KnowledgeDeleteResponse(BaseModel):
    deleted: bool


class ChatSourceResponse(BaseModel):
    document_id: UUID
    filename: str
    chunk_index: int
    heading: str | None
    chunk_text: str
    score: float


class ChatResponse(BaseModel):
    request_id: UUID
    experiment: Literal["threshold_v1"] | None
    variant: Literal["A", "B"] | None
    effective_min_score: float
    answer: str
    sources: list[ChatSourceResponse]
    conversation_id: None
    tool_calls: list[dict[str, Any]]


class FeedbackResponse(BaseModel):
    saved: bool
    request_id: UUID


class OrderItemResponse(BaseModel):
    product_name: str
    quantity: int
    price: float


class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    status: str
    items: list[OrderItemResponse]
    total_amount: float
    created_at: datetime
    delivered_at: datetime | None


class RefundEligibilityResponse(BaseModel):
    eligible: bool
    reason: str
    deadline: datetime | None


class RefundApplicationResponse(BaseModel):
    refund_id: UUID
    order_id: str
    status: str
    reason: str
    created_at: datetime


class PendingActionResponse(BaseModel):
    action_id: str
    action: Literal["apply_refund"]
    order_id: str
    reason: str
    requires_confirmation: bool


class AgentToolCallResponse(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    result: Any


class AgentChatResponse(BaseModel):
    answer: str
    tool_calls: list[AgentToolCallResponse]
    conversation_id: UUID
    pending_action: PendingActionResponse | None
    refund_application: RefundApplicationResponse | None = None
