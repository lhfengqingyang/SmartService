"""Exercise LangChain's tool loop without an external model or database."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

pytest.importorskip("langchain")
pytest.importorskip("langchain_openai")

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.ai.langchain_order_demo import make_order_tool, run_order_demo
from app.biz.orders import Order, OrderError


class ToolCallingFake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        assert [tool.name for tool in tools] == ["order_query"]
        return self


def _order() -> Order:
    return Order(
        order_id="demo-order",
        user_id="demo-user",
        status="delivered",
        total_amount=Decimal("29.90"),
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        delivered_at=None,
        items=(),
    )


def test_langchain_agent_calls_bound_user_order_tool():
    seen = []

    def query(order_id, user_id):
        seen.append((order_id, user_id))
        return _order()

    model = ToolCallingFake(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "order_query", "args": {"order_id": "demo-order"}, "id": "call_1"}]
            ),
            AIMessage(content="订单已送达，金额 29.90。"),
        ]
    )
    result = run_order_demo("查询 demo-order", "demo-user", model=model, query=query)
    assert seen == [("demo-order", "demo-user")]
    assert result["tool_results"][0]["name"] == "order_query"
    assert '"total_amount": "29.90"' in result["tool_results"][0]["content"]


def test_order_tool_does_not_accept_model_supplied_user_id():
    seen = []

    def query(order_id, user_id):
        seen.append(user_id)
        return _order()

    tool = make_order_tool("demo-user", query=query)
    assert set(tool.args) == {"order_id"}
    tool.invoke({"order_id": "demo-order", "user_id": "other-user"})
    assert seen == ["demo-user"]


def test_order_tool_returns_business_error():
    def missing(order_id, user_id):
        raise OrderError("ORDER_NOT_FOUND", "missing", 404)

    result = make_order_tool("demo-user", query=missing).invoke({"order_id": "demo-order"})
    assert '"error_code": "ORDER_NOT_FOUND"' in result


def test_agent_rejects_answer_without_order_query():
    model = ToolCallingFake(responses=[AIMessage(content="订单已送达。")])
    with pytest.raises(RuntimeError, match="did not call order_query"):
        run_order_demo("查询 demo-order", "demo-user", model=model)


def test_agent_rejects_answer_after_order_lookup_error():
    def missing(order_id, user_id):
        raise OrderError("ORDER_NOT_FOUND", "missing", 404)

    model = ToolCallingFake(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "order_query", "args": {"order_id": "demo-order"}, "id": "call_1"}]
            ),
            AIMessage(content="订单已送达。"),
        ]
    )
    with pytest.raises(RuntimeError, match="order_query failed"):
        run_order_demo("查询 demo-order", "demo-user", model=model, query=missing)
