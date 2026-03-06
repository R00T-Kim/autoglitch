from __future__ import annotations

from src.safety import SafetyController, SafetyViolation
from src.types import GlitchParameters


def test_safety_sanitizes_parameters_into_bounds() -> None:
    config = {
        "glitch": {
            "parameters": {
                "width": {"min": 0.0, "max": 50.0},
                "offset": {"min": 0.0, "max": 50.0},
                "voltage": {"min": -1.0, "max": 1.0},
                "repeat": {"min": 1, "max": 10},
                "ext_offset": {"min": 0.0, "max": 500.0},
            }
        },
        "safety": {
            "width_min": 5.0,
            "width_max": 40.0,
            "offset_min": 3.0,
            "offset_max": 35.0,
            "voltage_abs_max": 0.6,
            "repeat_min": 2,
            "repeat_max": 8,
            "ext_offset_min": 10.0,
            "ext_offset_max": 200.0,
        },
    }

    safety = SafetyController.from_config(config)
    params = GlitchParameters(width=1.0, offset=99.0, voltage=1.2, repeat=20, ext_offset=400.0)

    safe = safety.sanitize_params(params)
    assert safe.width == 5.0
    assert safe.offset == 35.0
    assert safe.voltage == 0.6
    assert safe.repeat == 8
    assert safe.ext_offset == 200.0


def test_safety_detects_invalid_limits() -> None:
    config = {
        "glitch": {
            "parameters": {
                "width": {"min": 0.0, "max": 50.0},
                "offset": {"min": 0.0, "max": 50.0},
                "voltage": {"min": -1.0, "max": 1.0},
                "repeat": {"min": 1, "max": 10},
                "ext_offset": {"min": 0.0, "max": 500.0},
            }
        },
        "safety": {
            "width_min": 10.0,
            "width_max": 2.0,
        },
    }

    safety = SafetyController.from_config(config)
    errors = safety.validate_config(config)

    assert any("width_min" in error for error in errors)


def test_safety_detects_ext_offset_range_outside_glitch_limits() -> None:
    config = {
        "glitch": {
            "parameters": {
                "width": {"min": 0.0, "max": 50.0},
                "offset": {"min": 0.0, "max": 50.0},
                "voltage": {"min": -1.0, "max": 1.0},
                "repeat": {"min": 1, "max": 10},
                "ext_offset": {"min": 0.0, "max": 100.0},
            }
        },
        "safety": {
            "ext_offset_min": 0.0,
            "ext_offset_max": 150.0,
        },
    }

    safety = SafetyController.from_config(config)
    errors = safety.validate_config(config)

    assert any(
        "safety.ext_offset range must be within glitch.parameters.ext_offset range" in error
        for error in errors
    )


def test_safety_rate_limit_raises_when_auto_throttle_disabled() -> None:
    config = {
        "glitch": {
            "parameters": {
                "width": {"min": 0.0, "max": 50.0},
                "offset": {"min": 0.0, "max": 50.0},
                "voltage": {"min": -1.0, "max": 1.0},
                "repeat": {"min": 1, "max": 10},
                "ext_offset": {"min": 0.0, "max": 500.0},
            }
        },
        "safety": {
            "max_trials_per_minute": 1,
            "auto_throttle": False,
        },
    }

    safety = SafetyController.from_config(config)
    params = GlitchParameters(width=10.0, offset=10.0, voltage=0.0, repeat=1)

    safety.pre_trial(params)
    safety.post_trial()

    try:
        safety.pre_trial(params)
    except SafetyViolation as exc:
        assert "rate limit" in str(exc)
    else:
        raise AssertionError("expected SafetyViolation")


def test_safety_reports_non_integer_rate_limit_config() -> None:
    config = {
        "glitch": {
            "parameters": {
                "width": {"min": 0.0, "max": 50.0},
                "offset": {"min": 0.0, "max": 50.0},
                "voltage": {"min": -1.0, "max": 1.0},
                "repeat": {"min": 1, "max": 10},
                "ext_offset": {"min": 0.0, "max": 100.0},
            }
        },
        "safety": {
            "max_trials_per_minute": "fast",
        },
    }

    baseline_safety = SafetyController.from_config({"glitch": config["glitch"], "safety": {}})
    safety = SafetyController(limits=baseline_safety.limits)
    errors = safety.validate_config(config)

    assert "safety.max_trials_per_minute must be an integer" in errors
    assert baseline_safety.limits.max_trials_per_minute is None


def test_safety_rejects_unsafe_ext_offset() -> None:
    config = {
        "glitch": {
            "parameters": {
                "width": {"min": 0.0, "max": 50.0},
                "offset": {"min": 0.0, "max": 50.0},
                "voltage": {"min": -1.0, "max": 1.0},
                "repeat": {"min": 1, "max": 10},
                "ext_offset": {"min": 0.0, "max": 100.0},
            }
        },
        "safety": {
            "ext_offset_min": 0.0,
            "ext_offset_max": 25.0,
        },
    }

    safety = SafetyController.from_config(config)
    params = GlitchParameters(width=10.0, offset=10.0, voltage=0.0, repeat=1, ext_offset=50.0)

    try:
        safety.pre_trial(params)
    except SafetyViolation as exc:
        assert "ext_offset" in str(exc)
    else:
        raise AssertionError("expected SafetyViolation")
