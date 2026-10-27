import pytest

from app.evals.compare import compare_reports


def report(rows):
    return {"cases": rows}


def case(case_id, availability, checks=None):
    return {"id": case_id, "kind": "rag", "availability": availability, "checks": checks or {}}


def test_comparison_separates_availability_from_paired_quality() -> None:
    before = report([case("one", "ok", {"valid_citation": False}), case("two", "error")])
    after = report([case("one", "ok", {"valid_citation": True}), case("two", "ok", {"valid_citation": True})])
    result = compare_reports(before, after)
    assert result["before_available"] == 1
    assert result["after_available"] == 2
    assert result["paired_available"] == 1
    assert result["paired_checks"]["valid_citation"] == {
        "paired": 1,
        "before_passed": 0,
        "after_passed": 1,
    }
    assert result["availability_transitions"]["error_to_ok"] == 1
    assert result["automated_signal"] == "improved_candidate"


def test_new_failures_prevent_false_improvement() -> None:
    before = report([case("one", "ok", {"valid_citation": False}), case("two", "ok", {"no_evidence": True})])
    after = report([case("one", "ok", {"valid_citation": True}), case("two", "error")])
    result = compare_reports(before, after)
    assert result["automated_signal"] == "regressed"
    assert result["paired_available"] == 1


def test_no_paired_success_is_insufficient() -> None:
    result = compare_reports(report([case("one", "error")]), report([case("one", "error")]))
    assert result["automated_signal"] == "insufficient_paired_cases"


def test_comparison_requires_identical_cases_and_checks() -> None:
    with pytest.raises(ValueError, match="same case ids"):
        compare_reports(report([case("one", "ok")]), report([case("two", "ok")]))
    with pytest.raises(ValueError, match="check names changed"):
        compare_reports(
            report([case("one", "ok", {"valid_citation": True})]),
            report([case("one", "ok", {"source_recall_at_k": True})]),
        )


def test_comparison_rejects_different_case_content() -> None:
    before = report([case("one", "ok", {"valid_citation": True})])
    after = report([case("one", "ok", {"valid_citation": True})])
    before["case_fingerprint"] = "a"
    after["case_fingerprint"] = "b"
    with pytest.raises(ValueError, match="fingerprints"):
        compare_reports(before, after)


def test_comparison_rejects_different_demo_data_snapshots() -> None:
    before = report([case("one", "ok")])
    after = report([case("one", "ok")])
    before["case_fingerprint"] = after["case_fingerprint"] = "same-cases"
    before["data_fingerprint"] = "old-data"
    after["data_fingerprint"] = "new-data"

    with pytest.raises(ValueError, match="demo data fingerprints"):
        compare_reports(before, after)
