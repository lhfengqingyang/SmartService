import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine
from app.main import app

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_TESTS") != "1",
        reason="set RUN_LIVE_TESTS=1 to use real PostgreSQL, Embedding, and LLM services",
    ),
]

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"


def test_live_knowledge_ingestion_rag_listing_and_deletion() -> None:
    document_id = None
    try:
        upload = client.post(
            "/api/v1/knowledge/upload",
            files={
                "file": (
                    "live_refund_policy.md",
                    (FIXTURES / "refund_policy.md").read_bytes(),
                    "text/markdown",
                )
            },
            data={
                "tenant_id": "live-demo",
                "owner_user_id": "live-user",
                "visibility": "private",
                "allowed_roles": "support",
            },
        )
        assert upload.status_code == 200, upload.text
        document_id = upload.json()["document_id"]

        listing = client.get(
            "/api/v1/knowledge/documents",
            params={"tenant_id": "live-demo", "user_id": "live-user", "roles": "support"},
        )
        assert listing.status_code == 200, listing.text
        assert document_id in {item["document_id"] for item in listing.json()["items"]}

        answer = client.post(
            "/api/v1/chat",
            json={
                "question": "商品签收后多少天内可以申请退款？",
                "tenant_id": "live-demo",
                "user_id": "live-user",
                "roles": ["support"],
                "top_k": 3,
                "min_score": 0.5,
            },
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["sources"]
        assert any(source["document_id"] == document_id for source in answer.json()["sources"])
    finally:
        if document_id is not None:
            deletion = client.delete(
                f"/api/v1/knowledge/documents/{document_id}",
                params={"tenant_id": "live-demo", "user_id": "live-user"},
            )
            assert deletion.status_code == 200, deletion.text


def test_live_agent_prepares_and_confirms_simulated_refund() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM biz.refund_applications WHERE order_id = 'demo-refundable'")
        )

    try:
        prepared = client.post(
            "/api/v1/agent/chat",
            json={
                "message": (
                    "请为订单 demo-refundable 准备模拟退款，原因是商品损坏。"
                    "请调用 refund_prepare，但不要声称退款已经完成。"
                ),
                "user_id": "demo-user",
            },
        )
        assert prepared.status_code == 200, prepared.text
        prepared_body = prepared.json()
        assert prepared_body["pending_action"]["order_id"] == "demo-refundable"

        confirmed = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "确认提交模拟退款申请",
                "user_id": "demo-user",
                "conversation_id": prepared_body["conversation_id"],
                "confirm_pending_action": True,
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["refund_application"]["status"] == "pending"
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM biz.refund_applications WHERE order_id = 'demo-refundable'")
            )
