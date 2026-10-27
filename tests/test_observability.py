import json

from app import observability
from app.ai.rag import RetrievedChunk


def test_rag_metric_records_distribution_without_request_content(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(observability.logger, "info", events.append)
    sources = tuple(
        RetrievedChunk(str(i), "doc-1", "private.md", i, None, "secret text", score)
        for i, score in enumerate((0.8, 0.65))
    )
    observability.record_rag_request(status_code=200, latency_ms=12.345, sources=sources)
    event = json.loads(events[-1])
    assert event["retrieved_count"] == 2
    assert event["top1_score"] == 0.8
    assert event["top2_gap"] == 0.15
    assert event["no_evidence"] is False
    assert "secret text" not in events[-1]
    assert "private.md" not in events[-1]


def test_rag_metric_distinguishes_no_evidence_from_failure(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(observability.logger, "info", events.append)
    observability.record_rag_request(status_code=200, latency_ms=3, sources=())
    observability.record_rag_request(status_code=502, latency_ms=4, error_code="LLM_UNAVAILABLE")
    no_evidence, failure = (json.loads(event) for event in events)
    assert no_evidence["no_evidence"] is True
    assert failure["no_evidence"] is False
    assert failure["error_code"] == "LLM_UNAVAILABLE"
