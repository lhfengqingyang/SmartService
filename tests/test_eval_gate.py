from app.evals.gate import evaluate_gate


def make_report(checks=None):
    return {
        "case_fingerprint": "fixed-cases",
        "data_fingerprint": "fixed-data",
        "cases": [{"id": "case-1", "availability": "ok", "checks": checks or {"valid_citation": True}}],
        "metrics": {},
    }


def make_review(*, fact_supported=True):
    return {
        "case_fingerprint": "fixed-cases",
        "data_fingerprint": "fixed-data",
        "reviews": [{"id": "case-1", "fact_supported": fact_supported, "safe": True, "note": "checked source"}],
    }


def test_gate_requires_human_fact_approval():
    decision = evaluate_gate(make_report(), make_review(fact_supported=False))

    assert decision["decision"] == "block"
    assert any("facts not approved" in reason for reason in decision["reasons"])


def test_gate_blocks_missing_business_tool_even_with_valid_citation():
    decision = evaluate_gate(make_report({"valid_citation": True, "required_tools_present": False}), make_review())

    assert decision["decision"] == "block"
    assert any("required_tools_present" in reason for reason in decision["reasons"])


def test_gate_blocks_regressed_comparison():
    comparison = {
        "case_count": 1,
        "case_content_verified": True,
        "data_content_verified": True,
        "automated_signal": "regressed",
    }

    decision = evaluate_gate(make_report(), make_review(), comparison=comparison)

    assert decision["decision"] == "block"


def test_gate_passes_reviewed_case_without_regression():
    decision = evaluate_gate(make_report(), make_review())

    assert decision == {"decision": "pass", "case_count": 1, "available": 1, "reasons": []}
