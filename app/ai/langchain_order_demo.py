"""Isolated, read-only LangChain exercise using the existing order service.

Run with ``python -m app.ai.langchain_order_demo --user-id ... --order-id ...``.
The supplied user ID is demo input, not authenticated identity.
"""

import argparse
import json
from collections.abc import Callable
from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

from app.biz.orders import Order, OrderError, get_order, validate_identifier
from app.config import LlmSettings, get_llm_settings


def make_order_tool(user_id: str, *, query: Callable[[str, str], Order] = get_order) -> Any:
    """Bind the requester outside model-controlled tool arguments."""
    validate_identifier(user_id, "user_id")

    @tool("order_query")
    def order_query(order_id: str) -> str:
        """Look up one order belonging to the current user by its exact order ID."""
        try:
            validate_identifier(order_id, "order_id")
            order = query(order_id, user_id)
        except OrderError as exc:
            return json.dumps({"ok": False, "error_code": exc.error_code}, ensure_ascii=False)
        return json.dumps(
            {
                "ok": True,
                "order_id": order.order_id,
                "status": order.status,
                "total_amount": str(order.total_amount),
            },
            ensure_ascii=False,
        )

    return order_query


def run_order_demo(
    question: str,
    user_id: str,
    *,
    settings: LlmSettings | None = None,
    query: Callable[[str, str], Order] = get_order,
    model: Any = None,
) -> dict[str, Any]:
    if not question.strip() or len(question) > 4000:
        raise ValueError("question must contain 1 to 4000 characters")
    order_tool = make_order_tool(user_id, query=query)
    if model is None:
        settings = settings or get_llm_settings()
        model = ChatOpenAI(
            model=settings.model,
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=15.0,
            max_retries=0,
            temperature=0.1,
        )
    agent = create_agent(
        model=model,
        tools=[order_tool],
        system_prompt=(
            "You answer questions about the current user's orders. "
            "Call order_query for order facts. Never invent order data. "
            "This demo can only read orders and cannot create refunds."
        ),
    )
    state = agent.invoke({"messages": [{"role": "user", "content": question}]}, config={"recursion_limit": 6})
    messages = state["messages"]
    tool_results = [
        {"name": message.name, "content": message.content}
        for message in messages
        if message.type == "tool"
    ]
    if not tool_results:
        raise RuntimeError("the agent did not call order_query")
    if any(json.loads(result["content"]).get("ok") is not True for result in tool_results):
        raise RuntimeError("order_query failed; no answer can be verified")
    return {"answer": str(messages[-1].content), "tool_results": tool_results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only LangChain order tool demo")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--order-id", required=True)
    args = parser.parse_args()
    validate_identifier(args.order_id, "order_id")
    result = run_order_demo(f"请查询订单 {args.order_id} 的状态和金额。", args.user_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
