from __future__ import annotations

from dataclasses import dataclass

from src.runtime.preflight import HilPreflightThresholds, run_hil_preflight
from src.types import GlitchParameters, RawResult


@dataclass
class _StaticHardware:
    response: RawResult

    def execute(self, _params: GlitchParameters) -> RawResult:
        return self.response


class _TimeoutHardware:
    def execute(self, _params: GlitchParameters) -> RawResult:
        raise TimeoutError("serial timeout")


def test_hil_preflight_passes_within_thresholds() -> None:
    hardware = _StaticHardware(
        response=RawResult(
            serial_output=b"boot ok", response_time=0.05, reset_detected=False, error_code=None
        )
    )

    result = run_hil_preflight(
        hardware=hardware,
        safe_params=GlitchParameters(width=10.0, offset=5.0, voltage=0.0, repeat=1),
        probe_trials=5,
        thresholds=HilPreflightThresholds(
            max_timeout_rate=0.2, max_reset_rate=0.2, max_p95_latency_s=0.5
        ),
        target_name="STM32F303",
        hardware_mode="serial",
    )

    assert result["valid"] is True
    assert result["metrics"]["timeout_rate"] == 0.0
    assert result["metrics"]["reset_rate"] == 0.0


def test_hil_preflight_fails_timeout_threshold() -> None:
    hardware = _TimeoutHardware()

    result = run_hil_preflight(
        hardware=hardware,
        safe_params=GlitchParameters(width=10.0, offset=5.0, voltage=0.0, repeat=1),
        probe_trials=4,
        thresholds=HilPreflightThresholds(
            max_timeout_rate=0.25, max_reset_rate=1.0, max_p95_latency_s=1.0
        ),
        target_name="ESP32",
        hardware_mode="serial",
    )

    assert result["valid"] is False
    assert "timeout_rate_exceeded" in result["reason_codes"]
    assert result["metrics"]["timeout_rate"] == 1.0
    assert result["exceptions"] == 4
