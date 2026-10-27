import httpx
import pytest

from app.ai.llm import LlmError, chat_completion
from app.config import LlmSettings

SETTINGS = LlmSettings(api_key="test-key", base_url="https://example.test/v4", model="test-model")


def test_chat_completion_returns_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://example.test/v4/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": " Answer [1]. "}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        answer = chat_completion([{"role": "user", "content": "Question"}], settings=SETTINGS, client=client)

    assert answer == "Answer [1]."


def test_chat_completion_rejects_invalid_response() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []}))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(LlmError, match="validation failed"):
            chat_completion([{"role": "user", "content": "Question"}], settings=SETTINGS, client=client)
