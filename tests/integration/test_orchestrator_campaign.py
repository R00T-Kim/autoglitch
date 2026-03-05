from __future__ import annotations

import json

from src.classifier import RuleBasedClassifier
from src.hardware import MockHardware
from src.logging_viz import ExperimentLogger
from src.mapper import PrimitiveMapper
from src.observer import BasicObserver
from src.optimizer import BayesianOptimizer
from src.orchestrator import ExperimentOrchestrator, OrchestratorState


def test_campaign_runs_and_writes_report(tmp_path) -> None:
    param_space = {
        "width": {"min": 0.0, "max": 50.0, "step": 0.1},
        "offset": {"min": 0.0, "max": 50.0, "step": 0.1},
        "voltage": {"min": -1.0, "max": 1.0},
        "repeat": {"min": 1, "max": 10},
    }

    optimizer = BayesianOptimizer(param_space, seed=123, n_initial=5)
    logger_viz = ExperimentLogger(output_dir=str(tmp_path / "logs"), run_id="test_run")

    orchestrator = ExperimentOrchestrator(
        optimizer=optimizer,
        hardware=MockHardware(seed=123),
        observer=BasicObserver(),
        classifier=RuleBasedClassifier(),
        mapper=PrimitiveMapper(),
        logger_viz=logger_viz,
        config={"target": {"name": "STM32F303"}, "experiment": {"seed": 123}},
    )

    campaign = orchestrator.run_campaign(n_trials=25)

    assert campaign.n_trials == 25
    assert orchestrator.state == OrchestratorState.DONE
    assert campaign.success_rate >= 0.0

    summary_path = logger_viz.write_campaign_summary(campaign, output_dir=str(tmp_path / "results"))
    assert summary_path.exists()

    payload = json.loads(summary_path.read_text())
    assert "primitive_repro_rate" in payload
    assert "time_to_first_primitive" in payload
