import json
import sys

import pytest

from app.evals.runner import DEFAULT_CASES, build_report, load_jsonl, main, score_case


def test_golden_cases_are_complete_and_reviewable() -> None:
    cases = load_jsonl(DEFAULT_CASES)

    assert len(cases) == 30
    assert sum(case["kind"] == "rag" for case in cases) == 20
    assert sum(case["kind"] == "agent" for case in cases) == 10
    assert all(case.get("review_notes") for case in cases)
    assert all("request" in case for case in cases)
    assert all(case.get("expected_chunks") for case in cases if case["kind"] == "rag" and case["answerable"])


def test_rag_checks_retrieval_and_citation_separately() -> None:
    case = {
        "id": "rag-1",
        "kind": "rag",
        "answerable": True,
        "expected_filenames": ["refund_policy.md"],
    }
    observation = {
        "id": "rag-1",
        "status_code": 200,
        "response": {
            "answer": "退款窗口为七天 [2]",
            "sources": [{"filename": "refund_policy.md"}],
        },
    }

    result = score_case(case, observation)

    assert result["checks"] == {"source_recall_at_k": True, "valid_citation": False}


def test_chunk_label_rejects_wrong_chunk_from_correct_file() -> None:
    case = {
        "id": "rag-1",
        "kind": "rag",
        "answerable": True,
        "expected_filenames": ["refund_policy.md"],
        "expected_chunks": [{"filename": "refund_policy.md", "chunk_index": 0}],
    }
    observation = {
        "status_code": 200,
        "response": {
            "answer": "退款窗口为七天 [1]",
            "sources": [{"filename": "refund_policy.md", "chunk_index": 1}],
        },
    }
    checks = score_case(case, observation)["checks"]
    assert checks == {"source_recall_at_k": True, "chunk_recall_at_k": False, "valid_citation": True}


def test_agent_checks_tool_arguments_and_pending_action() -> None:
    case = {
        "id": "agent-1",
        "kind": "agent",
        "expected_tools": ["refund_prepare"],
        "expected_order_id": "demo-refundable",
        "expected_pending": True,
    }
    observation = {
        "id": "agent-1",
        "status_code": 200,
        "response": {
            "tool_calls": [
                {"tool_name": "refund_prepare", "arguments": {"order_id": "demo-expired"}}
            ],
            "pending_action": {"order_id": "demo-refundable"},
        },
    }

    result = score_case(case, observation)

    assert result["checks"]["tool_selection"] is True
    assert result["checks"]["tool_arguments"] is False
    assert result["checks"]["pending_order_id"] is True


def test_agent_scoring_separates_missing_tool_from_redundant_read() -> None:
    case = {
        "id": "agent-1",
        "kind": "agent",
        "expected_tools": ["order_query", "refund_eligibility_check"],
        "expected_order_id": "demo-refundable",
        "expected_pending": False,
    }
    observation = {
        "status_code": 200,
        "response": {
            "tool_calls": [
                {"tool_name": "order_query", "arguments": {"order_id": "demo-refundable"}},
                {"tool_name": "order_query", "arguments": {"order_id": "demo-refundable"}},
            ],
            "pending_action": None,
        },
    }

    checks = score_case(case, observation)["checks"]

    assert checks["required_tools_present"] is False
    assert checks["no_duplicate_read"] is False
    assert checks["no_unexpected_prepare"] is True


def test_agent_scoring_rejects_unexpected_prepare() -> None:
    case = {
        "id": "agent-1",
        "kind": "agent",
        "expected_tools": ["order_query"],
        "expected_order_id": "demo-refundable",
        "expected_pending": False,
    }
    observation = {
        "status_code": 200,
        "response": {
            "tool_calls": [
                {"tool_name": "order_query", "arguments": {"order_id": "demo-refundable"}},
                {"tool_name": "refund_prepare", "arguments": {"order_id": "demo-refundable"}},
            ],
            "pending_action": None,
        },
    }

    assert score_case(case, observation)["checks"]["no_unexpected_prepare"] is False


def test_unavailable_model_does_not_reduce_quality_score() -> None:
    cases = [
        {
            "id": "agent-1",
            "kind": "agent",
            "expected_tools": ["order_query"],
            "expected_order_id": "demo-refundable",
            "expected_pending": False,
        }
    ]
    observations = [
        {
            "id": "agent-1",
            "status_code": 502,
            "response": {"error_code": "AGENT_UNAVAILABLE"},
        }
    ]

    report = build_report(cases, observations)

    assert report["available"] == 0
    assert report["errors"] == {"AGENT_UNAVAILABLE": 1}
    assert report["metrics"] == {}


def test_report_rejects_mixed_demo_data_snapshots() -> None:
    cases = [
        {"id": "one", "kind": "rag", "answerable": False, "expected_filenames": []},
        {"id": "two", "kind": "rag", "answerable": False, "expected_filenames": []},
    ]
    observations = [
        {"id": "one", "status_code": 502, "response": {"error_code": "LLM_UNAVAILABLE"}, "data_fingerprint": "a"},
        {"id": "two", "status_code": 502, "response": {"error_code": "LLM_UNAVAILABLE"}, "data_fingerprint": "b"},
    ]

    with pytest.raises(ValueError, match="different demo data fingerprints"):
        build_report(cases, observations)


def test_missing_observations_are_reported_explicitly() -> None:
    cases = [
        {
            "id": "rag-1",
            "kind": "rag",
            "answerable": False,
            "expected_filenames": [],
        }
    ]

    report = build_report(cases, [])

    assert report["case_count"] == 1
    assert report["observed"] == 0
    assert report["cases"][0]["availability"] == "missing"


def test_cli_scores_recorded_observation_and_writes_report(tmp_path, monkeypatch) -> None:
    cases = tmp_path / "cases.jsonl"
    observations = tmp_path / "observations.jsonl"
    report_path = tmp_path / "report.json"
    cases.write_text(
        json.dumps(
            {
                "id": "rag-1",
                "kind": "rag",
                "answerable": False,
                "expected_filenames": [],
                "request": {"question": "unknown"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    observations.write_text(
        json.dumps(
            {
                "id": "rag-1",
                "status_code": 200,
                "response": {
                    "answer": "现有知识库无法确认这个问题。",
                    "sources": [],
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--cases",
            str(cases),
            "--observations",
            str(observations),
            "--report",
            str(report_path),
        ],
    )

    main()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["metrics"]["no_evidence"] == {"passed": 1, "total": 1, "rate": 1.0}
    assert len(report["case_fingerprint"]) == 64
