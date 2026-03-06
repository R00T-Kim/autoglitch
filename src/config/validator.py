"""Configuration validation helpers."""

from __future__ import annotations

from typing import Any

from .schema import validate_autoglitch_config


def _safe_int(value: Any, *, label: str, errors: list[str]) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be an integer")
        return None


def _safe_float(value: Any, *, label: str, errors: list[str]) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be numeric")
        return None


def _safe_mapping(value: Any, *, label: str, errors: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    errors.append(f"{label} must be a mapping")
    return {}


def validate_config(config: dict[str, Any], mode: str = "strict") -> list[str]:
    """Return list of validation errors. Empty means valid.

    Args:
        config: Raw merged config payload.
        mode: Validation mode. ``strict`` uses the pydantic schema and ``legacy``
            uses the historical lightweight validator.
    """
    normalized_mode = str(mode or "strict").lower()
    if normalized_mode not in {"strict", "legacy"}:
        return [f"config validation mode must be one of: strict, legacy (got: {mode})"]

    if not isinstance(config, dict):
        return ["config must be a mapping"]

    if normalized_mode == "strict":
        return validate_autoglitch_config(config)

    return _validate_config_legacy(config)


def _validate_config_legacy(config: dict[str, Any]) -> list[str]:
    """Legacy hand-written validator kept for backward compatibility."""
    errors: list[str] = []

    config_version = config.get("config_version", 1)
    parsed_version = _safe_int(config_version, label="config_version", errors=errors)
    if parsed_version is not None and parsed_version not in {1, 2, 3}:
        errors.append(f"unsupported config_version: {config_version} (expected 1, 2 or 3)")

    required_top_keys = ["experiment", "optimizer", "glitch", "hardware"]
    for key in required_top_keys:
        if key not in config:
            errors.append(f"missing top-level key: {key}")

    optimizer_cfg = _safe_mapping(config.get("optimizer", {}), label="optimizer", errors=errors)
    glitch_cfg_raw = config.get("glitch", {})
    glitch_cfg = _safe_mapping(glitch_cfg_raw, label="glitch", errors=errors)
    glitch_params: dict[str, Any] | None
    if not isinstance(glitch_cfg_raw, dict):
        errors.append("glitch.parameters must be a mapping")
        glitch_params = None
    else:
        glitch_params = _safe_mapping(
            glitch_cfg.get("parameters", {}), label="glitch.parameters", errors=errors
        )
    safety_cfg = _safe_mapping(config.get("safety", {}), label="safety", errors=errors)

    glitch_ranges: dict[str, tuple[float, float]] = {}
    required_params = ("width", "offset", "voltage", "repeat")
    optional_params = ("ext_offset",)
    if glitch_params is not None:
        for param_name in (*required_params, *optional_params):
            if param_name not in glitch_params:
                if param_name in required_params:
                    errors.append(f"missing glitch.parameters.{param_name}")
                continue

            spec = glitch_params[param_name]
            if not isinstance(spec, dict):
                errors.append(f"glitch.parameters.{param_name} must be mapping")
                continue

            if "min" not in spec or "max" not in spec:
                errors.append(f"glitch.parameters.{param_name} must include min/max")
                continue

            min_v = _safe_float(
                spec["min"],
                label=f"glitch.parameters.{param_name}.min",
                errors=errors,
            )
            max_v = _safe_float(
                spec["max"],
                label=f"glitch.parameters.{param_name}.max",
                errors=errors,
            )
            if min_v is None or max_v is None:
                continue

            glitch_ranges[param_name] = (min_v, max_v)

            if min_v > max_v:
                errors.append(f"glitch.parameters.{param_name}.min must be <= max")

            if param_name == "ext_offset" and min_v < 0:
                errors.append("glitch.parameters.ext_offset.min must be >= 0")

            if "step" in spec:
                step = _safe_float(
                    spec["step"],
                    label=f"glitch.parameters.{param_name}.step",
                    errors=errors,
                )
                if step is None:
                    continue
                if step <= 0:
                    errors.append(f"glitch.parameters.{param_name}.step must be > 0")

    safety_pairs = (
        ("width", "width_min", "width_max"),
        ("offset", "offset_min", "offset_max"),
        ("repeat", "repeat_min", "repeat_max"),
        ("ext_offset", "ext_offset_min", "ext_offset_max"),
    )
    for glitch_name, min_key, max_key in safety_pairs:
        min_present = min_key in safety_cfg
        max_present = max_key in safety_cfg
        if not min_present and not max_present:
            continue

        parsed_min = _safe_float(safety_cfg.get(min_key), label=f"safety.{min_key}", errors=errors)
        parsed_max = _safe_float(safety_cfg.get(max_key), label=f"safety.{max_key}", errors=errors)
        if parsed_min is None or parsed_max is None:
            continue

        if parsed_min > parsed_max:
            errors.append(f"safety.{min_key} must be <= safety.{max_key}")

        if glitch_name == "ext_offset" and parsed_min < 0:
            errors.append("safety.ext_offset_min must be >= 0")

        glitch_range = glitch_ranges.get(glitch_name)
        if glitch_range is not None:
            glitch_min, glitch_max = glitch_range
            if parsed_min < glitch_min or parsed_max > glitch_max:
                errors.append(
                    "safety."
                    f"{glitch_name} range must be within "
                    f"glitch.parameters.{glitch_name} range"
                )

    if "voltage_abs_max" in safety_cfg:
        voltage_abs_max = _safe_float(
            safety_cfg.get("voltage_abs_max"),
            label="safety.voltage_abs_max",
            errors=errors,
        )
        if voltage_abs_max is not None and voltage_abs_max <= 0:
            errors.append("safety.voltage_abs_max must be > 0")

        voltage_range = glitch_ranges.get("voltage")
        if voltage_abs_max is not None and voltage_range is not None:
            glitch_min, glitch_max = voltage_range
            glitch_abs = max(abs(glitch_min), abs(glitch_max))
            if voltage_abs_max > glitch_abs:
                errors.append(
                    "safety.voltage_abs_max must be <= glitch.parameters.voltage abs range"
                )

    if "min_cooldown_s" in safety_cfg:
        min_cooldown_s = _safe_float(
            safety_cfg.get("min_cooldown_s"),
            label="safety.min_cooldown_s",
            errors=errors,
        )
        if min_cooldown_s is not None and min_cooldown_s < 0:
            errors.append("safety.min_cooldown_s must be >= 0")

    if "max_trials_per_minute" in safety_cfg and safety_cfg["max_trials_per_minute"] is not None:
        max_trials_per_minute = _safe_int(
            safety_cfg["max_trials_per_minute"],
            label="safety.max_trials_per_minute",
            errors=errors,
        )
        if max_trials_per_minute is not None and max_trials_per_minute <= 0:
            errors.append("safety.max_trials_per_minute must be > 0")

    optimizer_type = str(optimizer_cfg.get("type", "bayesian"))
    if optimizer_type not in {"bayesian", "rl"}:
        errors.append("optimizer.type must be one of: bayesian, rl")

    if "target" not in config:
        errors.append("target profile not merged; run with --target or --template")

    return errors
