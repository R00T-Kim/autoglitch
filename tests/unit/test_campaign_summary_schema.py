from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from src.logging_viz import ExperimentLogger
from src.types import (
    CampaignResult,
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


def test_campaign_summary_schema_v4_contains_runtime_latency_and_optimizer(tmp_path) -> None:
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
        config={"target": {"name": "STM32F303"}},
    )

    logger = ExperimentLogger(output_dir=str(tmp_path), run_id="run_test")
    summary_path = logger.write_campaign_summary(
        campaign,
        output_dir=str(tmp_path),
        mlflow_info={"enabled": False},
        optimizer_info={"enabled": True, "backend_in_use": "heuristic"},
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 4
    assert payload["runtime"]["throughput_trials_per_second"] > 0
    assert payload["latency"]["mean_seconds"] == pytest.approx(0.15)
    assert payload["pareto_front"]
    assert payload["optimizer_runtime"]["enabled"] is True
