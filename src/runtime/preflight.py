"""HIL preflight helpers for serial hardware stability checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from ..types import GlitchParameters, RawResult


@dataclass
class HilPreflightThresholds:
    """Acceptance thresholds for preflight checks."""

    max_timeout_rate: float = 0.05
    max_reset_rate: float = 0.10
    max_p95_latency_s: float = 0.50


def run_hil_preflight(
    *,
    hardware: Any,
    safe_params: GlitchParameters,
    probe_trials: int,
    thresholds: HilPreflightThresholds,
    target_name: str = "unknown",
    hardware_mode: str = "serial",
) -> dict[str, Any]:
    """Run N quick probe trials and evaluate serial HIL readiness."""
    trial_count = max(1, int(probe_trials))
    timeout_count = 0
    reset_count = 0
    exception_count = 0
    response_times: list[float] = []
    sample_errors: list[str] = []

    for _ in range(trial_count):
        try:
            raw: RawResult = hardware.execute(safe_params)
            response_times.append(max(0.0, float(raw.response_time)))

            if raw.reset_detected:
                reset_count += 1

            if not raw.serial_output:
                timeout_count += 1
        except Exception as exc:  # pragma: no cover - integration/runtime path
            exception_count += 1
            timeout_count += 1
            if len(sample_errors) < 5:
                sample_errors.append(str(exc))

    latency_mean_s = float(np.mean(response_times)) if response_times else 0.0
    latency_p95_s = (
        float(np.percentile(np.array(response_times, dtype=float), 95)) if response_times else 0.0
    )
    latency_max_s = float(max(response_times)) if response_times else 0.0

    timeout_rate = timeout_count / trial_count
    reset_rate = reset_count / trial_count

    reason_codes: list[str] = []
    if timeout_rate > thresholds.max_timeout_rate:
        reason_codes.append("timeout_rate_exceeded")
    if reset_rate > thresholds.max_reset_rate:
        reason_codes.append("reset_rate_exceeded")
    if latency_p95_s > thresholds.max_p95_latency_s:
        reason_codes.append("p95_latency_exceeded")
    if not response_times:
        reason_codes.append("no_successful_trials")

    return {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "target": target_name,
        "hardware_mode": hardware_mode,
        "probe_trials": trial_count,
        "completed_trials": len(response_times),
        "exceptions": exception_count,
        "metrics": {
            "timeout_rate": timeout_rate,
            "reset_rate": reset_rate,
            "latency_mean_s": latency_mean_s,
            "latency_p95_s": latency_p95_s,
            "latency_max_s": latency_max_s,
        },
        "thresholds": {
            "max_timeout_rate": thresholds.max_timeout_rate,
            "max_reset_rate": thresholds.max_reset_rate,
            "max_p95_latency_s": thresholds.max_p95_latency_s,
        },
        "safe_params": {
            "width": safe_params.width,
            "offset": safe_params.offset,
            "voltage": safe_params.voltage,
            "repeat": safe_params.repeat,
            "ext_offset": safe_params.ext_offset,
        },
        "reason_codes": reason_codes,
        "valid": len(reason_codes) == 0,
        "sample_errors": sample_errors,
    }
