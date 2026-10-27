import ast
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from smolagents import OpenAIServerModel, ToolCallingAgent
from smolagents.monitoring import LogLevel

from app.ai.rag import RequesterContext
from app.ai.tools import KnowledgeSearchTool, OrderQueryTool, RefundEligibilityTool, RefundPreparationTool
from app.config import LlmSettings, get_llm_settings

AgentFactory = Callable[[str], ToolCallingAgent]
logger = logging.getLogger(__name__)


class CustomerServiceAgentError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentAnswer:
    answer: str
    tool_calls: tuple["AgentToolCall", ...]


@dataclass(frozen=True)
class AgentToolCall:
    tool_name: str
    arguments: dict[str, Any]
    result: Any


AGENT_INSTRUCTIONS = """
You are a customer-service agent for simulated orders.
Use tools for every claim about an order or refund eligibility. Never invent tool results.
The tools are already bound to the current user; do not ask for or guess another user ID.
There is no tool that creates a refund. If the user asks to apply for a refund and provides a reason, call
refund_prepare. If no reason is provided, ask for it. A prepared action still requires explicit confirmation
through the application. Never treat ordinary affirmative language as execution and never claim money was refunded.
Keep the final answer concise and answer in the same language as the user.
""".strip()

GROUNDED_INSTRUCTIONS = """
For refund-policy tasks, search policy documents and query the actual order and refund eligibility.
Use source numbers such as [1] for policy claims. Never infer order facts from policy documents.
If evidence is missing, a tool fails, or policy and business results disagree, say that the case
requires human review. Never prepare a refund before verifying the order and eligibility.
""".strip()


def create_customer_service_agent(
    user_id: str,
    *,
    settings: LlmSettings | None = None,
    requester: RequesterContext | None = None,
) -> ToolCallingAgent:
    settings = settings or get_llm_settings()
    model = OpenAIServerModel(
        model_id=settings.model,
        api_base=settings.base_url,
        api_key=settings.api_key,
        client_kwargs={"timeout": 15.0, "max_retries": 0},
        retry=False,
        temperature=0.1,
        max_tokens=800,
    )
    trace = [] if requester is not None else None
    tools = [
        OrderQueryTool(user_id, trace=trace),
        RefundEligibilityTool(user_id, trace=trace),
        RefundPreparationTool(user_id, trace=trace),
    ]
    if requester is not None:
        tools.append(KnowledgeSearchTool(requester, trace=trace))
    agent = ToolCallingAgent(
        tools=tools,
        model=model,
        instructions=AGENT_INSTRUCTIONS + ("\n" + GROUNDED_INSTRUCTIONS if requester else ""),
        max_steps=6 if requester else 3,
        verbosity_level=LogLevel.OFF,
    )
    if trace is not None:
        agent.evidence_trace = trace
    return agent


def answer_business_question(
    message: str,
    user_id: str,
    *,
    agent_factory: AgentFactory = create_customer_service_agent,
    requester: RequesterContext | None = None,
    last_order_id: str | None = None,
) -> AgentAnswer:
    if not message.strip() or len(message) > 4000:
        raise ValueError("message must contain 1 to 4000 characters")
    if not user_id.strip() or len(user_id) > 64:
        raise ValueError("user_id must contain 1 to 64 characters")

    try:
        agent = agent_factory(user_id, requester=requester) if requester else agent_factory(user_id)
        task = message.strip()
        if last_order_id:
            task = f"Previous order ID in this user's conversation: {last_order_id}\nCurrent request: {task}"
        output = agent.run(task, reset=True)
    except Exception as exc:
        status_code = None
        current: BaseException | None = exc
        for _ in range(5):
            if current is None:
                break
            status_code = getattr(current, "status_code", None)
            if isinstance(status_code, int):
                break
            current = current.__cause__ or current.__context__
        if isinstance(status_code, int):
            logger.warning("Agent provider failed with HTTP %s", status_code)
        else:
            logger.warning("Agent execution failed: %s", type(exc).__name__)
        raise CustomerServiceAgentError("agent execution failed") from exc
    answer = str(output).strip()
    if not answer:
        raise CustomerServiceAgentError("agent returned an empty answer")
    tool_calls = []
    if requester is not None and hasattr(agent, "evidence_trace"):
        tool_calls = [AgentToolCall(name, arguments, result) for name, arguments, result in agent.evidence_trace]
    else:
        for step in getattr(getattr(agent, "memory", None), "steps", []):
            observations = getattr(step, "observations", None)
            for call in getattr(step, "tool_calls", None) or []:
                if call.name == "final_answer":
                    continue
                tool_calls.append(
                    AgentToolCall(
                        tool_name=call.name,
                        arguments=dict(call.arguments),
                        result=observations,
                    )
                )
    return AgentAnswer(answer=answer, tool_calls=tuple(tool_calls))


def parse_tool_result(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return None
    return parsed if isinstance(parsed, dict) else None


def verify_grounded_refund(result: AgentAnswer) -> tuple[bool, str | None]:
    """Gate model claims and prepared writes on successful policy and business evidence."""
    evidence: dict[str, dict[str, Any]] = {}
    for call in result.tool_calls:
        parsed = parse_tool_result(call.result)
        if call.tool_name in {"knowledge_search", "order_query", "refund_eligibility_check", "refund_prepare"}:
            if parsed is None or parsed.get("ok") is not True:
                return False, "知识或业务工具执行失败，需人工处理。"
            evidence[call.tool_name] = parsed
    sources = evidence.get("knowledge_search", {}).get("sources", [])
    if not sources:
        return False, "现有知识库证据不足，需人工核实退款政策。"
    if "order_query" not in evidence or "refund_eligibility_check" not in evidence:
        return False, "订单或退款资格未完成核验，需人工处理。"
    order = evidence["order_query"].get("order", {})
    eligibility = evidence["refund_eligibility_check"].get("eligibility", {})
    if not isinstance(order, dict) or not isinstance(eligibility, dict):
        return False, "业务工具结果无效，需人工处理。"
    order_ids = {
        call.arguments.get("order_id")
        for call in result.tool_calls
        if call.tool_name in {"order_query", "refund_eligibility_check", "refund_prepare"}
    }
    if len(order_ids) != 1 or order.get("order_id") not in order_ids:
        return False, "订单核验结果不一致，需人工处理。"
    if eligibility.get("eligible") not in {True, False}:
        return False, "退款资格结果无效，需人工处理。"
    if any(call.tool_name == "refund_prepare" for call in result.tool_calls) and not eligibility["eligible"]:
        return False, "订单不符合退款资格，不能准备申请。"
    prepared = evidence.get("refund_prepare")
    if prepared is not None:
        action = prepared.get("pending_action")
        if not isinstance(action, dict) or action.get("order_id") != order.get("order_id"):
            return False, "待确认动作与已核验订单不一致，需人工处理。"
    allowed_citations = {f"[{source['number']}]" for source in sources if "number" in source}
    if not any(citation in result.answer for citation in allowed_citations):
        return False, "政策回答缺少可核对的知识来源，需人工核实。"
    return True, None
