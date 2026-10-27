from fastapi.testclient import TestClient

from app.ai.rag import RagAnswer, RetrievedChunk
from app.api import chat
from app.main import app

client = TestClient(app)


def test_chat_endpoint_returns_answer_and_sources(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(chat, "record_rag_request", lambda **event: events.append(event))
    stored = []
    monkeypatch.setattr(chat, "save_rag_request", lambda *args: stored.append(args))
    source = RetrievedChunk(
        chunk_id="chunk-1",
        document_id="00000000-0000-0000-0000-000000000001",
        filename="refund_policy.md",
        chunk_index=0,
        heading="Refund policy > Time limit",
        chunk_text="Refunds are available within seven days.",
        score=0.82,
    )
    monkeypatch.setattr(chat, "answer_question", lambda *args, **kwargs: RagAnswer("Seven days [1].", (source,)))

    response = client.post(
        "/api/v1/chat",
        json={
            "question": "How long is the refund period?",
            "tenant_id": "tenant-a",
            "user_id": "user-1",
            "roles": ["support"],
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Seven days [1]."
    assert response.json()["request_id"]
    assert stored[0][3] == [0.82]
    assert response.json()["sources"][0]["filename"] == "refund_policy.md"
    assert events[0]["status_code"] == 200
    assert events[0]["sources"] == (source,)
    assert events[0]["latency_ms"] >= 0


def test_feedback_endpoint_passes_rating_and_optional_question(monkeypatch) -> None:
    saved = []
    monkeypatch.setattr(chat, "submit_rag_feedback", lambda *args: saved.append(args))
    response = client.post(
        "/api/v1/chat/feedback",
        json={
            "request_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "demo",
            "user_id": "demo-user",
            "rating": "unhelpful",
            "question": "What is the refund policy?",
        },
    )
    assert response.status_code == 200
    assert saved[0][3:] == ("unhelpful", "What is the refund policy?", None)


def test_experiment_assignment_is_stable_and_changes_threshold(monkeypatch) -> None:
    assigned = []
    monkeypatch.setattr(chat, "assign_variant", lambda tenant, user: "B")
    monkeypatch.setattr(chat, "answer_question", lambda *args, **kwargs: (
        assigned.append(kwargs["min_score"]) or RagAnswer("现有知识库无法确认这个问题。", ())
    ))
    monkeypatch.setattr(chat, "save_rag_request", lambda *args: assigned.append(args[-3:]))
    response = client.post(
        "/api/v1/chat",
        json={"question": "unknown", "tenant_id": "demo", "user_id": "demo-user", "experiment": "threshold_v1"},
    )
    assert response.status_code == 200
    assert response.json()["variant"] == "B"
    assert response.json()["effective_min_score"] == 0.6
    assert assigned == [0.6, ("threshold_v1", "B", 0.6)]


def test_variant_assignment_is_stable_per_user() -> None:
    assert chat.assign_variant("demo", "demo-user") == chat.assign_variant("demo", "demo-user")
    assert chat.assign_variant("demo", "demo-user") in {"A", "B"}
