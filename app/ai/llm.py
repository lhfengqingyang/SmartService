import logging
from collections.abc import Sequence

import httpx

from app.config import LlmSettings, get_llm_settings

logger = logging.getLogger(__name__)


class LlmError(RuntimeError):
    pass


def chat_completion(
    messages: Sequence[dict[str, str]],
    *,
    settings: LlmSettings | None = None,
    client: httpx.Client | None = None,
) -> str:
    if not messages:
        raise ValueError("messages must not be empty")

    settings = settings or get_llm_settings()
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        response = client.post(
            f"{settings.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            json={
                "model": settings.model,
                "messages": list(messages),
                "temperature": 0.1,
                "max_tokens": 800,
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        if isinstance(exc, httpx.HTTPStatusError):
            logger.warning("LLM provider returned HTTP %s", exc.response.status_code)
        else:
            logger.warning("LLM provider request failed: %s", type(exc).__name__)
        raise LlmError("LLM API request or response validation failed") from exc
    finally:
        if owns_client:
            client.close()

    if not isinstance(content, str) or not content.strip():
        raise LlmError("LLM API returned empty content")
    return content.strip()
