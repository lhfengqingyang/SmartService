from typing import Any

import pytest

from app.ai.rag import NO_EVIDENCE_ANSWER, RequesterContext, RetrievalError, answer_question, retrieve_chunks
from app.db.vector import to_vector_literal


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statement = ""
        self.parameters: dict[str, Any] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def execute(self, statement, parameters) -> FakeResult:
        self.statement = str(statement)
        self.parameters = parameters
        return FakeResult(self.rows)


class FakeEngine:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.connection = FakeConnection(rows)

    def connect(self) -> FakeConnection:
        return self.connection


def embedding_for_question(texts) -> list[list[float]]:
    assert texts == ["How long is the refund period?"]
    return [[0.1] * 1024]


def test_retrieve_chunks_applies_acl_and_similarity_in_sql() -> None:
    engine = FakeEngine(
        [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "filename": "refund_policy.md",
                "chunk_index": 0,
                "heading": "Refund policy > Time limit",
                "chunk_text": "Refunds are available within seven days.",
                "score": 0.82,
            }
        ]
    )

    chunks = retrieve_chunks(
        "How long is the refund period?",
        RequesterContext(tenant_id="tenant-a", user_id="user-1", roles=("support",)),
        top_k=3,
        min_score=0.6,
        embedder=embedding_for_question,
        engine=engine,
    )

    assert chunks[0].filename == "refund_policy.md"
    assert chunks[0].score == pytest.approx(0.82)
    assert "d.visibility = 'public'" in engine.connection.statement
    assert "d.allowed_roles && CAST(:roles AS text[])" in engine.connection.statement
    assert "ORDER BY c.embedding <=>" in engine.connection.statement
    assert engine.connection.parameters["tenant_id"] == "tenant-a"
    assert engine.connection.parameters["roles"] == ["support"]
    assert engine.connection.parameters["max_distance"] == pytest.approx(0.4)
    assert engine.connection.parameters["top_k"] == 3


@pytest.mark.parametrize(
    ("question", "top_k", "min_score"),
    [("", 5, 0.5), ("question", 0, 0.5), ("question", 5, 1.1)],
)
def test_retrieve_chunks_validates_parameters(question: str, top_k: int, min_score: float) -> None:
    with pytest.raises(ValueError):
        retrieve_chunks(
            question,
            RequesterContext(tenant_id="tenant-a", user_id="user-1"),
            top_k=top_k,
            min_score=min_score,
            embedder=embedding_for_question,
            engine=FakeEngine([]),
        )


def test_retrieve_chunks_rejects_wrong_embedding_dimension() -> None:
    with pytest.raises(RetrievalError, match="question embedding response is invalid"):
        retrieve_chunks(
            "question",
            RequesterContext(tenant_id="tenant-a", user_id="user-1"),
            embedder=lambda texts: [[0.1, 0.2]],
            engine=FakeEngine([]),
        )


def test_vector_literal_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite numbers"):
        to_vector_literal([float("nan")] * 1024)


def test_answer_question_skips_llm_without_evidence() -> None:
    called = False

    def chat(messages) -> str:
        nonlocal called
        called = True
        return "must not be called"

    result = answer_question(
        "How long is the refund period?",
        RequesterContext(tenant_id="tenant-a", user_id="user-1"),
        embedder=embedding_for_question,
        engine=FakeEngine([]),
        chat=chat,
    )

    assert result.answer == NO_EVIDENCE_ANSWER
    assert result.sources == ()
    assert called is False


def test_answer_question_builds_grounded_prompt() -> None:
    engine = FakeEngine(
        [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "filename": "refund_policy.md",
                "chunk_index": 0,
                "heading": "Refund policy > Time limit",
                "chunk_text": "Refunds are available within seven days.",
                "score": 0.82,
            }
        ]
    )

    def chat(messages) -> str:
        assert "只能依据" in messages[0]["content"]
        assert "不能回答‘代表已符合退款资格’" in messages[0]["content"]
        assert "Refunds are available within seven days" in messages[1]["content"]
        return "Refunds are available within seven days [1]."

    result = answer_question(
        "How long is the refund period?",
        RequesterContext(tenant_id="tenant-a", user_id="user-1"),
        embedder=embedding_for_question,
        engine=engine,
        chat=chat,
    )

    assert result.answer.endswith("[1].")
    assert len(result.sources) == 1
