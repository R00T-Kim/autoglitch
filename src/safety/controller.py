"""Safety policy enforcement for glitch campaigns."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from ..types import GlitchParameters


class SafetyViolation(RuntimeError):
    """Raised when safety constraints are violated."""


@dataclass
class SafetyLimits:
    """Safety threshold set for glitch operations."""

    width_min: float = 0.0
    width_max: float = 50.0
    offset_min: float = 0.0
    offset_max: float = 50.0
    voltage_abs_max: float = 1.0
    repeat_min: int = 1
    repeat_max: int = 10
    ext_offset_min: float = 0.0
    ext_offset_max: float = 1_000_000.0
    min_cooldown_s: float = 0.0
    max_trials_per_minute: int | None = None
    auto_throttle: bool = True


class SafetyController:
    """Validate and throttle trial execution to protect hardware."""

    def __init__(self, limits: SafetyLimits):
        self.limits = limits
        self._last_fire_ts: float | None = None
        self._recent_trials: deque[float] = deque()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> SafetyController:
        glitch_params = config.get("glitch", {}).get("parameters", {})
        safety_cfg = config.get("safety", {})

        width_cfg = glitch_params.get("width", {})
        offset_cfg = glitch_params.get("offset", {})
        repeat_cfg = glitch_params.get("repeat", {})
        voltage_cfg = glitch_params.get("voltage", {})
        ext_offset_cfg = glitch_params.get("ext_offset", {})

        voltage_abs = max(
            abs(float(voltage_cfg.get("min", -1.0))),
            abs(float(voltage_cfg.get("max", 1.0))),
        )

        limits = SafetyLimits(
            width_min=float(safety_cfg.get("width_min", width_cfg.get("min", 0.0))),
            width_max=float(safety_cfg.get("width_max", width_cfg.get("max", 50.0))),
            offset_min=float(safety_cfg.get("offset_min", offset_cfg.get("min", 0.0))),
            offset_max=float(safety_cfg.get("offset_max", offset_cfg.get("max", 50.0))),
            voltage_abs_max=float(safety_cfg.get("voltage_abs_max", voltage_abs)),
            repeat_min=int(safety_cfg.get("repeat_min", repeat_cfg.get("min", 1))),
            repeat_max=int(safety_cfg.get("repeat_max", repeat_cfg.get("max", 10))),
            ext_offset_min=float(safety_cfg.get("ext_offset_min", ext_offset_cfg.get("min", 0.0))),
            ext_offset_max=float(
                safety_cfg.get("ext_offset_max", ext_offset_cfg.get("max", 1_000_000.0))
            ),
            min_cooldown_s=float(safety_cfg.get("min_cooldown_s", 0.0)),
            max_trials_per_minute=(
                int(safety_cfg["max_trials_per_minute"])
                if safety_cfg.get("max_trials_per_minute") is not None
                else None
            ),
            auto_throttle=bool(safety_cfg.get("auto_throttle", True)),
        )
        return cls(limits)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        cfg = config.get("safety", {})
        glitch_cfg = config.get("glitch", {})
        glitch_params = glitch_cfg.get("parameters", {}) if isinstance(glitch_cfg, dict) else {}

        if self.limits.width_min > self.limits.width_max:
            errors.append("safety.width_min must be <= safety.width_max")
        if self.limits.offset_min > self.limits.offset_max:
            errors.append("safety.offset_min must be <= safety.offset_max")
        if self.limits.repeat_min > self.limits.repeat_max:
            errors.append("safety.repeat_min must be <= safety.repeat_max")
        if self.limits.ext_offset_min > self.limits.ext_offset_max:
            errors.append("safety.ext_offset_min must be <= safety.ext_offset_max")
        if self.limits.voltage_abs_max <= 0:
            errors.append("safety.voltage_abs_max must be > 0")
        if self.limits.ext_offset_min < 0:
            errors.append("safety.ext_offset_min must be >= 0")
        if self.limits.min_cooldown_s < 0:
            errors.append("safety.min_cooldown_s must be >= 0")

        if "max_trials_per_minute" in cfg and cfg["max_trials_per_minute"] is not None:
            try:
                max_trials_per_minute = int(cfg["max_trials_per_minute"])
            except (TypeError, ValueError):
                errors.append("safety.max_trials_per_minute must be an integer")
            else:
                if max_trials_per_minute <= 0:
                    errors.append("safety.max_trials_per_minute must be > 0")

        ext_offset_cfg = glitch_params.get("ext_offset", {})
        if isinstance(ext_offset_cfg, dict):
            try:
                ext_offset_min = float(ext_offset_cfg.get("min", self.limits.ext_offset_min))
                ext_offset_max = float(ext_offset_cfg.get("max", self.limits.ext_offset_max))
            except (TypeError, ValueError):
                errors.append("glitch.parameters.ext_offset min/max must be numeric")
            else:
                if (
                    self.limits.ext_offset_min < ext_offset_min
                    or self.limits.ext_offset_max > ext_offset_max
                ):
                    errors.append(
                        "safety.ext_offset range must be within glitch.parameters.ext_offset range"
                    )
        elif "ext_offset" in glitch_params:
            errors.append("glitch.parameters.ext_offset must be mapping")

        return errors

    def sanitize_params(self, params: GlitchParameters) -> GlitchParameters:
        """Clamp suggested parameters to safe boundaries."""
        return GlitchParameters(
            width=max(self.limits.width_min, min(self.limits.width_max, float(params.width))),
            offset=max(self.limits.offset_min, min(self.limits.offset_max, float(params.offset))),
            voltage=max(
                -self.limits.voltage_abs_max,
                min(self.limits.voltage_abs_max, float(params.voltage)),
            ),
            repeat=max(self.limits.repeat_min, min(self.limits.repeat_max, int(params.repeat))),
            ext_offset=max(
                self.limits.ext_offset_min,
                min(self.limits.ext_offset_max, float(params.ext_offset)),
            ),
        )

    def pre_trial(self, params: GlitchParameters) -> None:
        """Enforce cooldown and rate limits before firing trial."""
        self._validate_params(params)
        self._enforce_cooldown()
        self._enforce_rate_limit()

    def post_trial(self) -> None:
        now = time.monotonic()
        self._last_fire_ts = now
        self._recent_trials.append(now)
        self._prune_recent(now)

    def _validate_params(self, params: GlitchParameters) -> None:
        if not (self.limits.width_min <= params.width <= self.limits.width_max):
            raise SafetyViolation(f"unsafe width: {params.width}")
        if not (self.limits.offset_min <= params.offset <= self.limits.offset_max):
            raise SafetyViolation(f"unsafe offset: {params.offset}")
        if abs(params.voltage) > self.limits.voltage_abs_max:
            raise SafetyViolation(f"unsafe voltage: {params.voltage}")
        if not (self.limits.repeat_min <= params.repeat <= self.limits.repeat_max):
            raise SafetyViolation(f"unsafe repeat: {params.repeat}")
        if not (self.limits.ext_offset_min <= params.ext_offset <= self.limits.ext_offset_max):
            raise SafetyViolation(f"unsafe ext_offset: {params.ext_offset}")

    def _enforce_cooldown(self) -> None:
        if self.limits.min_cooldown_s <= 0 or self._last_fire_ts is None:
            return

        elapsed = time.monotonic() - self._last_fire_ts
        wait_s = self.limits.min_cooldown_s - elapsed
        if wait_s <= 0:
            return

        if self.limits.auto_throttle:
            time.sleep(wait_s)
            return

        raise SafetyViolation(
            f"cooldown violation: wait {wait_s:.3f}s (min={self.limits.min_cooldown_s:.3f}s)"
        )

    def _enforce_rate_limit(self) -> None:
        max_trials = self.limits.max_trials_per_minute
        if max_trials is None:
            return

        now = time.monotonic()
        self._prune_recent(now)
        if len(self._recent_trials) < max_trials:
            return

        oldest = self._recent_trials[0]
        wait_s = 60.0 - (now - oldest)
        if wait_s <= 0:
            return

        if self.limits.auto_throttle:
            time.sleep(wait_s)
            now = time.monotonic()
            self._prune_recent(now)
            return

        raise SafetyViolation(
            f"rate limit violation: max_trials_per_minute={max_trials}, wait={wait_s:.3f}s"
        )

    def _prune_recent(self, now: float) -> None:
        while self._recent_trials and (now - self._recent_trials[0]) > 60.0:
            self._recent_trials.popleft()
