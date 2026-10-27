from collections.abc import Sequence

import httpx

from app.config import EmbeddingSettings, get_embedding_settings


class EmbeddingError(RuntimeError):
    pass


def embed_texts(
    texts: Sequence[str],
    *,
    settings: EmbeddingSettings | None = None,
    client: httpx.Client | None = None,
) -> list[list[float]]:
    if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("texts must contain at least one non-empty string")

    settings = settings or get_embedding_settings()
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)

    try:
        response = client.post(
            f"{settings.base_url}/embeddings",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            json={
                "model": settings.model,
                "input": list(texts),
                "dimensions": settings.dimensions,
            },
        )
        response.raise_for_status()
        payload = response.json()
        items = sorted(payload["data"], key=lambda item: item["index"])
        vectors = [item["embedding"] for item in items]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise EmbeddingError("Embedding API request or response validation failed") from exc
    finally:
        if owns_client:
            client.close()

    if len(vectors) != len(texts):
        raise EmbeddingError("Embedding response count does not match input count")
    if any(len(vector) != settings.dimensions for vector in vectors):
        actual_dimensions = sorted({len(vector) for vector in vectors})
        raise EmbeddingError(
            f"Embedding dimension mismatch: expected {settings.dimensions}, got {actual_dimensions}"
        )
    if any(not all(isinstance(value, (int, float)) for value in vector) for vector in vectors):
        raise EmbeddingError("Embedding response contains non-numeric values")

    return vectors
