import pytest

from app.ai.agent import CustomerServiceAgentError, answer_business_question


class FakeAgent:
    def __init__(self, output="Order found") -> None:
        self.output = output
        self.calls = []

    def run(self, message: str, reset: bool):
        self.calls.append((message, reset))
        return self.output


def test_answer_business_question_runs_fresh_agent_for_bound_user() -> None:
    agent = FakeAgent()
    users = []

    def factory(user_id: str):
        users.append(user_id)
        return agent

    result = answer_business_question("  Query order-1  ", "trusted-user", agent_factory=factory)

    assert result.answer == "Order found"
    assert result.tool_calls == ()
    assert users == ["trusted-user"]
    assert agent.calls == [("Query order-1", True)]


def test_answer_business_question_maps_agent_failure() -> None:
    class BrokenAgent:
        def run(self, message: str, reset: bool):
            raise RuntimeError("secret provider error")

    with pytest.raises(CustomerServiceAgentError, match="agent execution failed"):
        answer_business_question("query", "user-1", agent_factory=lambda user_id: BrokenAgent())
