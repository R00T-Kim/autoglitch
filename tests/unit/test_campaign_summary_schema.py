from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from src.logging_viz import ExperimentLogger
from src.types import (
    CampaignResult,
    ExecutionMetadata,
    ExploitPrimitive,
    ExploitPrimitiveType,
    FaultClass,
    GlitchParameters,
    Observation,
    RawResult,
    TrialResult,
)


def _trial(
    *,
    trial_id: int,
    response_time: float,
    fault_class: FaultClass,
    primitive_type: ExploitPrimitiveType,
    confidence: float,
    timestamp: datetime,
) -> TrialResult:
    return TrialResult(
        trial_id=trial_id,
        parameters=GlitchParameters(width=10.0, offset=5.0, voltage=0.0, repeat=1),
        observation=Observation(
            raw=RawResult(
                serial_output=b"ok",
                response_time=response_time,
                reset_detected=False,
                error_code=None,
            ),
            timestamp=timestamp,
        ),
        fault_class=fault_class,
        primitive=ExploitPrimitive(type=primitive_type, confidence=confidence),
        execution=ExecutionMetadata(status="ok", origin="hardware"),
        timestamp=timestamp,
        metadata={"error_category": "none"},
    )


def test_campaign_latency_metrics_and_pareto_properties() -> None:
    start = datetime(2026, 3, 5, 12, 0, 0)
    campaign = CampaignResult(
        campaign_id="campaign_test",
        trials=[
            _trial(
                trial_id=1,
                response_time=0.30,
                fault_class=FaultClass.CRASH,
                primitive_type=ExploitPrimitiveType.NONE,
                confidence=0.0,
                timestamp=start,
            ),
            _trial(
                trial_id=2,
                response_time=0.10,
                fault_class=FaultClass.AUTH_BYPASS,
                primitive_type=ExploitPrimitiveType.CODE_EXECUTION,
                confidence=0.9,
                timestamp=start + timedelta(seconds=2),
            ),
        ],
        config={"target": {"name": "STM32F303"}},
    )

    assert campaign.latency_mean_seconds == pytest.approx(0.20)
    assert campaign.latency_max_seconds == pytest.approx(0.30)
    assert campaign.throughput_trials_per_second == pytest.approx(1.0)

    front = campaign.pareto_front
    assert len(front) == 1
    assert front[0]["trial_id"] == 2


def test_campaign_summary_schema_v8_contains_execution_and_bundle_fields(tmp_path) -> None:
    start = datetime(2026, 3, 5, 12, 0, 0)
    campaign = CampaignResult(
        campaign_id="campaign_test",
        trials=[
            _trial(
                trial_id=1,
                response_time=0.20,
                fault_class=FaultClass.NORMAL,
                primitive_type=ExploitPrimitiveType.NONE,
                confidence=0.0,
                timestamp=start,
            ),
            _trial(
                trial_id=2,
                response_time=0.10,
                fault_class=FaultClass.DATA_CORRUPTION,
                primitive_type=ExploitPrimitiveType.MEMORY_WRITE,
                confidence=0.7,
                timestamp=start + timedelta(seconds=1),
            ),
        ],
        config={
            "target": {"name": "STM32F303"},
            "run_tag": "unit",
            "ai": {"mode": "agentic_shadow"},
            "optimizer": {
                "bo": {"objective_mode": "multi", "multi_objective_weights": {"reward": 1.0}}
            },
            "_planner_backend": "heuristic",
            "_advisor_backend": "disabled",
            "_runtime_fingerprint": {
                "config_hash_sha256": "abc",
                "git_sha": "deadbeef",
                "git_dirty": False,
                "python_version": "3.12.0",
                "platform": "linux",
            },
        },
    )
    campaign.planner_events.append({"trace_id": "trace_1", "applied": False})
    campaign.policy_reject_count = 1
    campaign.agentic_interventions = 0

    logger = ExperimentLogger(output_dir=str(tmp_path), run_id="run_test")
    summary_path = logger.write_campaign_summary(
        campaign,
        output_dir=str(tmp_path),
        mlflow_info={"enabled": False},
        optimizer_info={"enabled": True, "backend_in_use": "heuristic"},
        component_plugins={
            "observer": "basic-observer",
            "classifier": "rule-classifier",
            "mapper": "primitive-mapper",
        },
        benchmark={"benchmark_id": "bench_unit", "task": "det_fault"},
    )
    manifest_path = logger.write_run_manifest(
        campaign.config, output_dir=str(tmp_path), plugin_snapshot=[]
    )
    logger.log_path.write_text("", encoding="utf-8")
    bundle = logger.write_artifact_bundle(
        summary_path=summary_path,
        manifest_path=manifest_path,
        log_path=logger.log_path,
        output_dir=str(tmp_path),
        hardware_resolution={
            "source": "unit-test",
            "binding": {"adapter_id": "mock-hardware", "location": "mock://local"},
            "target": "STM32F303",
        },
        benchmark={"benchmark_id": "bench_unit", "task": "det_fault", "backend": "mock-hardware"},
        lab={"operator": "tester", "board_id": "board-1"},
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 8
    assert payload["runtime"]["throughput_trials_per_second"] > 0
    assert payload["latency"]["mean_seconds"] == pytest.approx(0.15)
    assert payload["pareto_front"]
    assert payload["optimizer_runtime"]["enabled"] is True
    assert payload["reproducibility"]["config_hash_sha256"] == "abc"
    assert payload["objective_summary"]["mode"] == "multi"
    assert payload["run_tag"] == "unit"
    assert payload["agentic"]["mode"] == "agentic_shadow"
    assert payload["agentic"]["policy_reject_count"] == 1
    assert payload["agentic"]["planner_backend"] == "heuristic"
    assert payload["execution_status_breakdown"]["ok"] == 2
    assert payload["infra_failure_count"] == 0
    assert payload["time_to_first_valid_fault"] == 2
    assert payload["decision_trace"]
    assert payload["component_plugins"]["observer"] == "basic-observer"
    assert payload["artifact_bundle"] == bundle["bundle_dir"]
    assert payload["bundle_manifest"] == bundle["manifest"]
    assert payload["benchmark"]["benchmark_id"] == "bench_unit"
    assert Path(bundle["manifest"]).exists()


def test_log_trial_serializes_dataclass_payload_to_jsonl(tmp_path) -> None:
    logger = ExperimentLogger(output_dir=str(tmp_path), run_id="jsonl_test")
    trial = _trial(
        trial_id=7,
        response_time=0.05,
        fault_class=FaultClass.AUTH_BYPASS,
        primitive_type=ExploitPrimitiveType.CODE_EXECUTION,
        confidence=0.95,
        timestamp=datetime(2026, 3, 6, 12, 0, 0),
    )
    trial.observation.features = np.array([1.0, 2.0, 3.0], dtype=float)

    logger.log_trial(trial)

    payload = json.loads(logger.log_path.read_text(encoding="utf-8").strip())
    assert payload["trial_id"] == 7
    assert payload["observation"]["raw"]["serial_output"] == "ok"
    assert payload["observation"]["features"] == [1.0, 2.0, 3.0]
