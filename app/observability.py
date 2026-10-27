import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from app.ai.rag import RetrievedChunk

logger = logging.getLogger("smartservice.metrics")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.propagate = False


def record_rag_request(
    *,
    status_code: int,
    latency_ms: float,
    sources: Sequence[RetrievedChunk] = (),
    error_code: str | None = None,
) -> None:
    scores = [source.score for source in sources]
    event = {
        "event": "rag_request",
        "timestamp": datetime.now(UTC).isoformat(),
        "status_code": status_code,
        "latency_ms": round(latency_ms, 2),
        "retrieved_count": len(scores),
        "top1_score": round(scores[0], 4) if scores else None,
        "top2_gap": round(scores[0] - scores[1], 4) if len(scores) > 1 else None,
        "no_evidence": status_code == 200 and not scores,
        "error_code": error_code,
    }
    logger.info(json.dumps(event, ensure_ascii=False))
