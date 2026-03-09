from __future__ import annotations

from src.cli import compare_summary_to_report, summarize_trial_records


def test_summarize_trial_records_computes_metrics() -> None:
    trials = [
        {
            "trial_id": 1,
            "fault_class": "NORMAL",
            "primitive": {"type": "NONE"},
            "execution": {"status": "ok"},
        },
        {
            "trial_id": 2,
            "fault_class": "CRASH",
            "primitive": {"type": "MEMORY_READ"},
            "execution": {"status": "infra_failure"},
        },
        {
            "trial_id": 3,
            "fault_class": "AUTH_BYPASS",
            "primitive": {"type": "CODE_EXECUTION"},
            "execution": {"status": "ok"},
        },
    ]

    summary = summarize_trial_records(trials)

    assert summary["n_trials"] == 3
    assert summary["time_to_first_valid_fault"] == 3
    assert summary["time_to_first_primitive"] == 2
    assert summary["success_rate"] == 1 / 3
    assert summary["primitive_repro_rate"] == 1 / 3
    assert summary["infra_failure_count"] == 1
    assert summary["execution_status_breakdown"]["infra_failure"] == 1


def test_compare_summary_to_report_detects_match() -> None:
    summary = {
        "n_trials": 3,
        "success_rate": 0.5,
        "primitive_repro_rate": 0.5,
        "time_to_first_primitive": 2,
    }

    report = {
        "n_trials": 3,
        "success_rate": 0.5,
        "primitive_repro_rate": 0.5,
        "time_to_first_primitive": 2,
    }

    result = compare_summary_to_report(summary, report)
    assert result["all_match"] is True
