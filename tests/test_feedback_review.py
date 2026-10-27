import pytest

from app.evals.feedback_review import promote_approved
from app.evals.runner import score_case


def candidate() -> dict:
    return {
        "id": "feedback-00000000-0000-0000-0000-000000000001",
        "kind": "rag",
        "request": {
            "question": "签收后多久可以退款？",
            "tenant_id": "demo",
            "user_id": "demo-user",
            "roles": ["support"],
        },
        "approved": False,
        "answerable": None,
        "expected_filenames": [],
        "review_notes": "",
        "failure_type": None,
        "feedback_comment": "answer was unclear",
    }


def test_unreviewed_negative_feedback_never_becomes_a_case() -> None:
    assert promote_approved([candidate()]) == []


def test_approved_feedback_becomes_scored_case_without_comment() -> None:
    reviewed = candidate()
    reviewed.update(
        approved=True,
        answerable=True,
        expected_filenames=["refund_policy.md"],
        review_notes="核对签收后 7 个自然日及对应来源。",
        failure_type="answer_unsupported",
    )
    case = promote_approved([reviewed])[0]
    assert "feedback_comment" not in case
    result = score_case(
        case,
        {
            "status_code": 200,
            "response": {"answer": "签收后 7 天 [1]", "sources": [{"filename": "refund_policy.md"}]},
        },
    )
    assert result["checks"] == {"source_recall_at_k": True, "valid_citation": True}


def test_approval_requires_human_labels() -> None:
    reviewed = candidate()
    reviewed["approved"] = True
    with pytest.raises(ValueError, match="complete human labels"):
        promote_approved([reviewed])


def test_cannot_approve_and_reject_same_feedback() -> None:
    reviewed = candidate()
    reviewed.update(approved=True, rejected=True)
    with pytest.raises(ValueError, match="cannot approve and reject"):
        promote_approved([reviewed])


def test_approved_feedback_id_must_be_uuid() -> None:
    reviewed = candidate()
    reviewed.update(approved=True, failure_type="other", answerable=False, review_notes="No evidence")
    reviewed["id"] = "feedback-not-a-uuid"
    with pytest.raises(ValueError, match="invalid feedback case id"):
        promote_approved([reviewed])
