"""Configuration validation helpers."""
from __future__ import annotations

from typing import Any, Dict, List


def validate_config(config: Dict[str, Any]) -> List[str]:
    """Return list of validation errors. Empty means valid."""
    errors: List[str] = []

    config_version = config.get("config_version", 1)
    if int(config_version) != 1:
        errors.append(f"unsupported config_version: {config_version} (expected 1)")

    required_top_keys = ["experiment", "optimizer", "glitch", "hardware"]
    for key in required_top_keys:
        if key not in config:
            errors.append(f"missing top-level key: {key}")

    glitch_params = config.get("glitch", {}).get("parameters", {})
    for param_name in ("width", "offset", "voltage", "repeat"):
        if param_name not in glitch_params:
            errors.append(f"missing glitch.parameters.{param_name}")
            continue

        spec = glitch_params[param_name]
        if not isinstance(spec, dict):
            errors.append(f"glitch.parameters.{param_name} must be mapping")
            continue

        if "min" not in spec or "max" not in spec:
            errors.append(f"glitch.parameters.{param_name} must include min/max")
            continue

        min_v = float(spec["min"])
        max_v = float(spec["max"])
        if min_v > max_v:
            errors.append(f"glitch.parameters.{param_name}.min must be <= max")

        if "step" in spec:
            step = float(spec["step"])
            if step <= 0:
                errors.append(f"glitch.parameters.{param_name}.step must be > 0")

    optimizer_type = str(config.get("optimizer", {}).get("type", "bayesian"))
    if optimizer_type not in {"bayesian", "rl"}:
        errors.append("optimizer.type must be one of: bayesian, rl")

    if "target" not in config:
        errors.append("target profile not merged; run with --target or --template")

    return errors
