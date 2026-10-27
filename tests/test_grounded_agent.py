import pytest
from fastapi.testclient import TestClient

from app.ai.agent import AgentAnswer, AgentToolCall, answer_business_question, verify_grounded_refund
from app.ai.conversations import ConversationStore
from app.ai.rag import RequesterContext, RetrievalError, RetrievedChunk
from app.ai.tools import KnowledgeSearchTool
from app.api import agent as agent_api
from app.main import app

client = TestClient(app)


def _result(*, with_source=True, eligible=True, prepared=False) -> AgentAnswer:
    calls = [
        AgentToolCall(
            "knowledge_search",
            {"question": "退款政策"},
            {"ok": True, "sources": [{"number": 1, "filename": "refund_policy.md"}] if with_source else []},
        ),
        AgentToolCall(
            "order_query",
            {"order_id": "order-1"},
            {"ok": True, "order": {"order_id": "order-1", "status": "delivered"}},
        ),
        AgentToolCall(
            "refund_eligibility_check",
            {"order_id": "order-1"},
            {"ok": True, "eligibility": {"eligible": eligible}},
        ),
    ]
    if prepared:
        calls.append(
            AgentToolCall(
                "refund_prepare",
                {"order_id": "order-1", "reason": "damaged"},
                {"ok": True, "pending_action": {"order_id": "order-1", "reason": "damaged"}},
            )
        )
    return AgentAnswer("政策见 [1]，订单已核验。", tuple(calls))


def test_knowledge_tool_binds_acl_and_handles_missing_evidence() -> None:
    requester = RequesterContext("tenant-1", "user-1", ("support",))
    seen = []

    def search(question, context, *, top_k, min_score):
        seen.append((question, context, top_k, min_score))
        return [RetrievedChunk("chunk-1", "doc-1", "policy.md", 0, None, "七天内可申请", 0.8)]

    tool = KnowledgeSearchTool(requester, search=search)
    result = tool(question="退款期限")
    assert seen == [("退款期限", requester, 5, 0.5)]
    assert result["sources"][0]["text"] == "七天内可申请"

    def fail(*args, **kwargs):
        raise RetrievalError("DATABASE_UNAVAILABLE", "secret database error")

    failure = KnowledgeSearchTool(requester, search=fail)(question="退款期限")
    assert failure == {"ok": False, "error_code": "DATABASE_UNAVAILABLE", "sources": []}


def test_grounded_verifier_blocks_missing_policy_and_unsafe_prepare() -> None:
    assert verify_grounded_refund(_result())[0] is True
    assert verify_grounded_refund(_result(with_source=False))[0] is False
    assert verify_grounded_refund(_result(eligible=False, prepared=True))[0] is False
    bad_order = _result()
    calls = list(bad_order.tool_calls)
    calls[1] = AgentToolCall("order_query", {"order_id": "another-order"}, calls[1].result)
    assert verify_grounded_refund(AgentAnswer(bad_order.answer, tuple(calls)))[0] is False
    assert verify_grounded_refund(AgentAnswer("没有引用", bad_order.tool_calls))[0] is False
    failed_search = list(bad_order.tool_calls)
    failed_search[0] = AgentToolCall("knowledge_search", {"question": "退款政策"}, {"ok": False})
    assert verify_grounded_refund(AgentAnswer(bad_order.answer, tuple(failed_search)))[0] is False


def test_agent_uses_structured_tool_trace_for_grounded_task() -> None:
    class FakeAgent:
        evidence_trace = [(call.tool_name, call.arguments, call.result) for call in _result().tool_calls]

        def run(self, message, reset):
            assert reset is True
            assert "Previous order ID" in message
            return "政策见 [1]"

    result = answer_business_question(
        "继续处理", "user-1", requester=RequesterContext("tenant-1", "user-1"),
        last_order_id="order-1", agent_factory=lambda user_id, requester: FakeAgent(),
    )
    assert verify_grounded_refund(result)[0] is True
    assert isinstance(result.tool_calls[0].result, dict)


def test_grounded_agent_keeps_order_context_across_turns(monkeypatch) -> None:
    store = ConversationStore()
    monkeypatch.setattr(agent_api, "conversation_store", store)
    contexts = []

    def answer(message, user_id, *, requester, last_order_id):
        contexts.append((requester, last_order_id))
        return _result(prepared=len(contexts) == 2)

    monkeypatch.setattr(agent_api, "answer_business_question", answer)
    first = client.post(
        "/api/v1/agent/chat",
        json={"message": "订单退款政策", "user_id": "user-1", "tenant_id": "tenant-1", "task_mode": "refund_policy"},
    )
    assert first.status_code == 200
    assert first.json()["pending_action"] is None
    second = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "商品损坏，帮我申请",
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "task_mode": "refund_policy",
            "conversation_id": first.json()["conversation_id"],
        },
    )
    assert second.status_code == 200
    assert second.json()["pending_action"]["requires_confirmation"] is True
    assert contexts[1][1] == "order-1"
    assert contexts[0][0] == RequesterContext("tenant-1", "user-1", ())


def test_grounded_agent_fails_closed_when_policy_missing(monkeypatch) -> None:
    store = ConversationStore()
    monkeypatch.setattr(agent_api, "conversation_store", store)
    monkeypatch.setattr(
        agent_api, "answer_business_question", lambda *args, **kwargs: _result(with_source=False, prepared=True)
    )
    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "申请退款", "user_id": "user-1", "tenant_id": "tenant-1", "task_mode": "refund_policy"},
    )
    assert response.status_code == 200
    assert response.json()["pending_action"] is None
    assert store.get_or_create("user-1", response.json()["conversation_id"]).pending_refund is None


@pytest.mark.parametrize("fault", ["missing_eligibility", "failed_eligibility", "wrong_order"])
def test_grounded_agent_does_not_save_pending_action_after_tool_fault(monkeypatch, fault: str) -> None:
    store = ConversationStore()
    monkeypatch.setattr(agent_api, "conversation_store", store)
    result = _result(prepared=True)
    calls = list(result.tool_calls)
    if fault == "missing_eligibility":
        calls = [call for call in calls if call.tool_name != "refund_eligibility_check"]
    elif fault == "failed_eligibility":
        calls[2] = AgentToolCall("refund_eligibility_check", {"order_id": "order-1"}, {"ok": False})
    else:
        calls[1] = AgentToolCall(
            "order_query", {"order_id": "order-1"}, {"ok": True, "order": {"order_id": "different-order"}}
        )
    monkeypatch.setattr(
        agent_api, "answer_business_question", lambda *args, **kwargs: AgentAnswer(result.answer, tuple(calls))
    )

    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "申请退款", "user_id": "user-1", "tenant_id": "tenant-1", "task_mode": "refund_policy"},
    )

    assert response.status_code == 200
    assert response.json()["pending_action"] is None
    assert "需人工处理" in response.json()["answer"]
    assert store.get_or_create("user-1", response.json()["conversation_id"]).pending_refund is None
