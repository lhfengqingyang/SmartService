import os
from functools import partial
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai import knowledge as knowledge_service
from app.ai import rag as rag_service
from app.ai.agent import AgentAnswer, AgentToolCall
from app.ai.conversations import ConversationStore
from app.ai.tools import RefundPreparationTool
from app.api import agent as agent_api
from app.api import chat as chat_api
from app.api import knowledge as knowledge_api
from app.db.connection import check_database, get_engine
from app.evals.feedback_review import complete_reviews, export_candidates, sync_queue
from app.main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DB_INTEGRATION") != "1",
        reason="set RUN_DB_INTEGRATION=1 to use local PostgreSQL without external model APIs",
    ),
]

client = TestClient(app)
FIXTURE = Path(__file__).parent / "fixtures" / "knowledge" / "refund_policy.md"


def fake_embeddings(texts):
    return (
        [[1.0, 0.0] + [0.0] * 1022 if "签收" in value else [0.0, 1.0] + [0.0] * 1022 for value in texts]
    )


def fake_chat(messages):
    assert "退款" in messages[1]["content"]
    return "用户可在签收后 7 个自然日内申请模拟退款 [1]。"


def test_local_db_knowledge_answer_feedback_and_review_queue(monkeypatch) -> None:
    check_database()
    monkeypatch.setattr(
        knowledge_api,
        "import_document",
        partial(knowledge_service.import_document, embedder=fake_embeddings),
    )
    monkeypatch.setattr(
        chat_api,
        "answer_question",
        partial(rag_service.answer_question, embedder=fake_embeddings, chat=fake_chat),
    )
    tenant_id = f"test-{uuid4().hex}"
    user_id = "integration-user"
    document_id = None
    request_id = None
    try:
        upload = client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("refund_policy.md", FIXTURE.read_bytes(), "text/markdown")},
            data={"tenant_id": tenant_id, "owner_user_id": user_id, "visibility": "private"},
        )
        assert upload.status_code == 200, upload.text
        document_id = upload.json()["document_id"]

        answer = client.post(
            "/api/v1/chat",
            json={"question": "商品签收后几天可以申请模拟退款？", "tenant_id": tenant_id, "user_id": user_id},
        )
        assert answer.status_code == 200, answer.text
        body = answer.json()
        request_id = UUID(body["request_id"])
        assert body["sources"][0]["document_id"] == document_id
        assert "[1]" in body["answer"]

        feedback = client.post(
            "/api/v1/chat/feedback",
            json={
                "request_id": str(request_id),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "rating": "unhelpful",
                "question": "商品签收后几天可以申请模拟退款？",
            },
        )
        assert feedback.status_code == 200, feedback.text
        assert sync_queue(request_id) == 1
        assert sync_queue(request_id) == 0
        assert any(row["id"] == f"feedback-{request_id}" for row in export_candidates())
        complete_reviews([{"id": f"feedback-{request_id}", "rejected": True}])
        assert not any(row["id"] == f"feedback-{request_id}" for row in export_candidates())
    finally:
        with get_engine().begin() as connection:
            if request_id is not None:
                connection.execute(
                    text("DELETE FROM ai.rag_requests WHERE id=CAST(:id AS uuid)"),
                    {"id": str(request_id)},
                )
            if document_id is not None:
                connection.execute(text("DELETE FROM ai.documents WHERE id=CAST(:id AS uuid)"), {"id": document_id})


def test_local_db_agent_requires_confirmation_before_refund(monkeypatch) -> None:
    check_database()
    monkeypatch.setattr(agent_api, "conversation_store", ConversationStore())
    order_id = f"test-{uuid4().hex}"
    user_id = "integration-user"
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "INSERT INTO biz.orders (id,user_id,status,total_amount,delivered_at) "
                "VALUES (:id,:user_id,'completed',42,now()-interval '2 days')"
            ),
            {"id": order_id, "user_id": user_id},
        )
    try:
        order = client.get(f"/api/v1/orders/{order_id}", params={"user_id": user_id})
        assert order.status_code == 200
        eligibility = client.post(
            "/api/v1/refunds/check-eligibility",
            json={"order_id": order_id, "user_id": user_id},
        )
        assert eligibility.status_code == 200
        assert eligibility.json()["eligible"] is True

        def prepared_answer(message, bound_user_id):
            result = RefundPreparationTool(bound_user_id).forward(order_id, "商品损坏")
            return AgentAnswer(
                "model wording is replaced by the server",
                (AgentToolCall("refund_prepare", {"order_id": order_id, "reason": "商品损坏"}, result),),
            )

        monkeypatch.setattr(agent_api, "answer_business_question", prepared_answer)
        prepared = client.post(
            "/api/v1/agent/chat",
            json={"message": f"为 {order_id} 准备模拟退款", "user_id": user_id},
        )
        assert prepared.status_code == 200, prepared.text
        body = prepared.json()
        assert body["pending_action"]["order_id"] == order_id
        assert "confirm_pending_action=true" in body["answer"]
        with get_engine().connect() as connection:
            assert connection.execute(
                text("SELECT count(*) FROM biz.refund_applications WHERE order_id=:id"),
                {"id": order_id},
            ).scalar_one() == 0

        confirmed = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "确认",
                "user_id": user_id,
                "conversation_id": body["conversation_id"],
                "confirm_pending_action": True,
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["refund_application"]["status"] == "pending"
        with get_engine().connect() as connection:
            assert connection.execute(
                text("SELECT count(*) FROM biz.refund_applications WHERE order_id=:id"),
                {"id": order_id},
            ).scalar_one() == 1
    finally:
        with get_engine().begin() as connection:
            connection.execute(text("DELETE FROM biz.refund_applications WHERE order_id=:id"), {"id": order_id})
            connection.execute(text("DELETE FROM biz.orders WHERE id=:id"), {"id": order_id})
