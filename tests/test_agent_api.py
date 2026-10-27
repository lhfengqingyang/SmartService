import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.ai.agent import AgentAnswer, AgentToolCall, CustomerServiceAgentError
from app.ai.conversations import ConversationStore, PendingRefund
from app.api import agent
from app.biz.refunds import RefundApplication
from app.main import app

client = TestClient(app)


def use_empty_conversation_store(monkeypatch) -> ConversationStore:
    store = ConversationStore()
    monkeypatch.setattr(agent, "conversation_store", store)
    return store


def test_agent_chat_returns_answer_and_tool_trace(monkeypatch) -> None:
    use_empty_conversation_store(monkeypatch)
    result = AgentAnswer(
        answer="The order is eligible.",
        tool_calls=(
            AgentToolCall(
                tool_name="refund_eligibility_check",
                arguments={"order_id": "order-1"},
                result={"ok": True, "eligibility": {"eligible": True}},
            ),
        ),
    )
    monkeypatch.setattr(agent, "answer_business_question", lambda message, user_id: result)

    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "Can order-1 be refunded?", "user_id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "The order is eligible."
    assert response.json()["tool_calls"][0]["tool_name"] == "refund_eligibility_check"
    assert response.json()["conversation_id"] is not None
    assert response.json()["pending_action"] is None


def test_agent_chat_maps_provider_failure(monkeypatch) -> None:
    use_empty_conversation_store(monkeypatch)
    def fail(message: str, user_id: str):
        raise CustomerServiceAgentError("agent execution failed")

    monkeypatch.setattr(agent, "answer_business_question", fail)
    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "query order", "user_id": "user-1"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "agent execution failed", "error_code": "AGENT_UNAVAILABLE"}


def test_agent_chat_saves_and_confirms_structured_refund_action(monkeypatch) -> None:
    store = use_empty_conversation_store(monkeypatch)
    prepared = AgentAnswer(
        answer="Please confirm the simulated refund.",
        tool_calls=(
            AgentToolCall(
                tool_name="refund_prepare",
                arguments={"order_id": "order-1", "reason": "damaged"},
                result={
                    "ok": True,
                    "pending_action": {
                        "action": "apply_refund",
                        "order_id": "order-1",
                        "reason": "damaged",
                    },
                },
            ),
        ),
    )
    monkeypatch.setattr(agent, "answer_business_question", lambda message, user_id: prepared)
    created = RefundApplication(
        refund_id="00000000-0000-0000-0000-000000000001",
        order_id="order-1",
        user_id="user-1",
        status="pending",
        reason="damaged",
        idempotency_key="unused",
        created_at=datetime(2026, 10, 23, tzinfo=UTC),
    )
    apply_calls = []

    def fake_apply(*args, **kwargs):
        apply_calls.append((args, kwargs))
        return created

    monkeypatch.setattr(agent, "apply_refund", fake_apply)

    prepare_response = client.post(
        "/api/v1/agent/chat",
        json={"message": "Refund order-1 because it is damaged", "user_id": "user-1"},
    )
    body = prepare_response.json()
    assert prepare_response.status_code == 200
    assert body["pending_action"]["requires_confirmation"] is True
    assert "confirm_pending_action=true" in body["answer"]
    assert "仅回复“确认”不会创建申请" in body["answer"]
    assert "Please confirm" not in body["answer"]
    conversation_id = body["conversation_id"]

    confirm_response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "confirm",
            "user_id": "user-1",
            "conversation_id": conversation_id,
            "confirm_pending_action": True,
        },
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["refund_application"]["status"] == "pending"
    assert store.get_or_create("user-1", conversation_id).pending_refund is None
    assert apply_calls[0][0][:3] == ("order-1", "user-1", "damaged")
    assert apply_calls[0][1] == {"confirmed": True}


def test_agent_chat_reads_smolagents_string_observation(monkeypatch) -> None:
    use_empty_conversation_store(monkeypatch)
    prepared = AgentAnswer(
        answer="Please confirm.",
        tool_calls=(
            AgentToolCall(
                tool_name="refund_prepare",
                arguments={"order_id": "order-1", "reason": "damaged"},
                result=(
                    "{'ok': True, 'pending_action': {'action': 'apply_refund', "
                    "'order_id': 'order-1', 'reason': 'damaged'}}"
                ),
            ),
        ),
    )
    monkeypatch.setattr(agent, "answer_business_question", lambda message, user_id: prepared)

    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "refund order-1 because it is damaged", "user_id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["pending_action"]["order_id"] == "order-1"


def test_agent_chat_rejects_conversation_owned_by_another_user(monkeypatch) -> None:
    store = use_empty_conversation_store(monkeypatch)
    conversation = store.get_or_create("user-1")
    store.set_pending_refund(
        conversation.conversation_id,
        PendingRefund("action-1", "order-1", "damaged"),
    )

    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "confirm",
            "user_id": "user-2",
            "conversation_id": conversation.conversation_id,
            "confirm_pending_action": True,
        },
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "CONVERSATION_NOT_FOUND"


def test_agent_chat_enforces_total_timeout(monkeypatch) -> None:
    use_empty_conversation_store(monkeypatch)

    async def slow_threadpool(*args, **kwargs):
        await asyncio.sleep(0.02)

    monkeypatch.setattr(agent, "run_in_threadpool", slow_threadpool)
    monkeypatch.setattr(agent, "AGENT_TOTAL_TIMEOUT_SECONDS", 0.001)

    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "query order", "user_id": "user-1"},
    )

    assert response.status_code == 504
    assert response.json()["error_code"] == "AGENT_TIMEOUT"


def test_agent_chat_cancels_pending_action_without_calling_model(monkeypatch) -> None:
    store = use_empty_conversation_store(monkeypatch)
    conversation = store.get_or_create("user-1")
    store.set_pending_refund(
        conversation.conversation_id,
        PendingRefund("action-1", "order-1", "damaged"),
    )

    def must_not_run(*args, **kwargs):
        raise AssertionError("model must not be called while cancelling")

    monkeypatch.setattr(agent, "answer_business_question", must_not_run)
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "cancel",
            "user_id": "user-1",
            "conversation_id": conversation.conversation_id,
            "cancel_pending_action": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["pending_action"] is None
    assert store.get_or_create("user-1", conversation.conversation_id).pending_refund is None


def test_agent_chat_rejects_confirm_and_cancel_together(monkeypatch) -> None:
    use_empty_conversation_store(monkeypatch)
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "do both",
            "user_id": "user-1",
            "confirm_pending_action": True,
            "cancel_pending_action": True,
        },
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_REQUEST"
