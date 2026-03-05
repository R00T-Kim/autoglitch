from __future__ import annotations

from src.classifier import RuleBasedClassifier
from src.logging_viz import ExperimentLogger
from src.mapper import PrimitiveMapper
from src.observer import BasicObserver
from src.optimizer import BayesianOptimizer
from src.orchestrator import ExperimentOrchestrator
from src.runtime import CircuitBreaker, RecoveryExecutor, RetryPolicy
from src.safety import SafetyController
from src.types import GlitchParameters, RawResult


class FlakyHardware:
    def __init__(self, fail_times: int = 2):
        self.fail_times = fail_times
        self.calls = 0

    def execute(self, params: GlitchParameters) -> RawResult:  # noqa: ARG002
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient serial failure")

        return RawResult(
            serial_output=b"auth bypass success",
            response_time=0.02,
            reset_detected=False,
            error_code=None,
        )


def test_orchestrator_recovers_from_transient_hardware_error(tmp_path) -> None:
    param_space = {
        "width": {"min": 0.0, "max": 50.0, "step": 0.1},
        "offset": {"min": 0.0, "max": 50.0, "step": 0.1},
        "voltage": {"min": -1.0, "max": 1.0},
        "repeat": {"min": 1, "max": 10},
    }

    config = {
        "glitch": {"parameters": param_space},
        "safety": {
            "width_min": 0.0,
            "width_max": 50.0,
            "offset_min": 0.0,
            "offset_max": 50.0,
            "voltage_abs_max": 1.0,
            "repeat_min": 1,
            "repeat_max": 10,
            "min_cooldown_s": 0.0,
            "max_trials_per_minute": None,
            "auto_throttle": True,
        },
        "experiment": {"seed": 42},
        "target": {"name": "STM32F303"},
    }

    optimizer = BayesianOptimizer(param_space, seed=42, n_initial=1, backend="heuristic")
    logger_viz = ExperimentLogger(output_dir=str(tmp_path / "logs"), run_id="recovery_test")

    orchestrator = ExperimentOrchestrator(
        optimizer=optimizer,
        hardware=FlakyHardware(fail_times=2),
        observer=BasicObserver(),
        classifier=RuleBasedClassifier(),
        mapper=PrimitiveMapper(),
        logger_viz=logger_viz,
        config=config,
        safety_controller=SafetyController.from_config(config),
        recovery_executor=RecoveryExecutor(
            retry=RetryPolicy(max_attempts=3, initial_backoff_s=0.0, max_backoff_s=0.0),
            breaker=CircuitBreaker(failure_threshold=5, recovery_timeout_s=5.0),
        ),
    )

    trial = orchestrator.run_trial()

    assert trial.metadata["recovery"]["attempts"] == 3
    assert trial.metadata["recovery"]["recovered"] is True
    assert trial.observation.raw.error_code is None
