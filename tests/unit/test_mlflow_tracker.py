from __future__ import annotations

from src.logging_viz import MLflowTracker


def test_mlflow_tracker_disabled_by_default_snapshot() -> None:
    tracker = MLflowTracker(enabled=False, tracking_uri="mlruns", experiment_name="autoglitch")
    snapshot = tracker.snapshot()
    assert snapshot["enabled"] is False
    assert snapshot["run_id"] is None


def test_mlflow_tracker_handles_missing_dependency_gracefully() -> None:
    tracker = MLflowTracker(enabled=True, tracking_uri="mlruns", experiment_name="autoglitch")
    snapshot = tracker.snapshot()

    if snapshot["enabled"]:
        tracker.start_run(run_name="unit-test", tags={"suite": "unit"}, params={"p": 1})
        tracker.log_metrics({"metric": 0.5}, step=1)
        tracker.end_run()
        assert tracker.snapshot()["run_id"] is not None
    else:
        assert snapshot["disabled_reason"] is not None
