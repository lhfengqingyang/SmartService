import httpx
import pytest

from app.ai.embedding import EmbeddingError, embed_texts
from app.config import EmbeddingSettings, get_embedding_settings


def make_settings(dimensions: int = 3) -> EmbeddingSettings:
    return EmbeddingSettings(
        api_key="test-key",
        base_url="https://example.test/v4",
        model="embedding-test",
        dimensions=dimensions,
    )


def test_embed_texts_returns_vectors_in_index_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://example.test/v4/embeddings"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        vectors = embed_texts(["first", "second"], settings=make_settings(), client=client)

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


def test_embed_texts_rejects_unexpected_dimension() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
    )

    with httpx.Client(transport=transport) as client:
        with pytest.raises(EmbeddingError, match="dimension mismatch"):
            embed_texts(["text"], settings=make_settings(), client=client)


def test_embedding_settings_rejects_placeholder_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_API_KEY", "your_zhipu_api_key_here")

    with pytest.raises(RuntimeError, match="not configured"):
        get_embedding_settings()
