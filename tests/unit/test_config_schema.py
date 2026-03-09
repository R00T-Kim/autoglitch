from __future__ import annotations

import copy
from pathlib import Path

import yaml

from src.cli import _load_config
from src.config import validate_config
from src.config.schema import parse_autoglitch_config


def _merged_default() -> dict:
    return _load_config(Path("configs/default.yaml"), "stm32f3")


def test_strict_schema_accepts_default_merged_config() -> None:
    config = _merged_default()
    errors = validate_config(config, mode="strict")
    assert errors == []
    parsed = parse_autoglitch_config(config)
    assert parsed.config_version == 3
    assert parsed.target.name == "STM32F303"


def test_strict_schema_rejects_string_numeric_values() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["experiment"]["seed"] = "42"

    errors = validate_config(config, mode="strict")
    assert any("experiment.seed" in item for item in errors)


def test_strict_schema_requires_config_version_3() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["config_version"] = 1

    errors = validate_config(config, mode="strict")
    assert any("config_version" in item and "requires config_version: 3" in item for item in errors)


def test_legacy_mode_keeps_backward_compatibility_for_numeric_strings() -> None:
    with Path("configs/default.yaml").open("r", encoding="utf-8") as handle:
        base = yaml.safe_load(handle)
    with Path("configs/targets/stm32f3.yaml").open("r", encoding="utf-8") as handle:
        target = yaml.safe_load(handle)

    merged = {**base, "target": target["target"]}
    merged["experiment"]["seed"] = "42"
    merged["optimizer"]["type"] = "bayesian"

    errors = validate_config(merged, mode="legacy")
    assert errors == []


def test_legacy_mode_returns_errors_instead_of_raising_on_bad_version() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["config_version"] = "abc"

    errors = validate_config(config, mode="legacy")
    assert any(item == "config_version must be an integer" for item in errors)


def test_legacy_mode_returns_friendly_errors_for_non_mapping_sections() -> None:
    config = {
        "config_version": 1,
        "experiment": {},
        "optimizer": "broken",
        "glitch": [],
        "hardware": {},
    }

    errors = validate_config(config, mode="legacy")
    assert "optimizer must be a mapping" in errors
    assert "glitch must be a mapping" in errors
    assert "glitch.parameters must be a mapping" in errors


def test_legacy_mode_validates_ext_offset_and_safety_ranges() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["config_version"] = 1
    config["glitch"]["parameters"]["ext_offset"]["min"] = -1.0
    config["safety"]["ext_offset_max"] = 2_000_000.0

    errors = validate_config(config, mode="legacy")
    assert "glitch.parameters.ext_offset.min must be >= 0" in errors
    assert any(
        "safety.ext_offset range must be within glitch.parameters.ext_offset range" in item
        for item in errors
    )


def test_strict_schema_rejects_invalid_serial_preflight_threshold() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["hardware"]["serial"]["preflight"]["max_timeout_rate"] = 1.5

    errors = validate_config(config, mode="strict")
    assert any("max_timeout_rate" in item for item in errors)


def test_strict_schema_accepts_new_bo_backend_and_objective_mode() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["optimizer"]["bo"]["backend"] = "turbo"
    config["optimizer"]["bo"]["objective_mode"] = "multi"
    config["optimizer"]["bo"]["multi_objective_weights"] = {"reward": 1.0, "exploration": 0.5}

    errors = validate_config(config, mode="strict")
    assert errors == []


def test_strict_schema_rejects_negative_multi_objective_weight() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["optimizer"]["bo"]["multi_objective_weights"] = {"reward": -1.0}

    errors = validate_config(config, mode="strict")
    assert any("multi_objective_weights" in item for item in errors)


def test_strict_schema_accepts_agentic_config_defaults() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["ai"]["mode"] = "agentic_shadow"
    config["ai"]["planner_interval_trials"] = 10
    config["policy"]["max_patch_delta"] = 0.8

    errors = validate_config(config, mode="strict")
    assert errors == []


def test_strict_schema_accepts_component_plugin_selection() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["components"] = {
        "observer": "basic-observer",
        "classifier": "rule-classifier",
        "mapper": "primitive-mapper",
    }

    errors = validate_config(config, mode="strict")
    assert errors == []


def test_strict_schema_accepts_chipwhisperer_benchmark_and_lab_sections() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["hardware"]["adapter"] = "chipwhisperer-hardware"
    config["hardware"]["chipwhisperer"] = {
        "scope_name": "Husky",
        "serial_number": "CW123",
        "default_setup": True,
        "glitch_mode": "voltage",
        "glitch_output": "glitch_only",
        "trigger_src": "manual",
        "target_serial_port": "/dev/ttyUSB9",
        "target_baudrate": 115200,
        "target_timeout": 1.0,
        "capture_timeout_s": 0.25,
    }
    config["benchmark"] = {
        "enabled": True,
        "benchmark_id": "bench_stm32f3",
        "task": "det_fault",
        "backends": ["mock-hardware", "chipwhisperer-hardware"],
        "operator": "alice",
        "board_id": "board-1",
        "session_id": "2026-03-09",
    }
    config["lab"] = {
        "operator": "alice",
        "board_id": "board-1",
        "session_id": "2026-03-09",
        "wiring_profile": "wire-a",
        "board_prep_profile": "prep-a",
        "power_profile": "psu-a",
    }

    errors = validate_config(config, mode="strict")
    assert errors == []


def test_strict_schema_rejects_unknown_core_keys() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["experiment"]["surprise_toggle"] = True

    errors = validate_config(config, mode="strict")
    assert any("unknown keys not allowed" in item for item in errors)


def test_strict_schema_allows_x_extension_keys() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["x_runtime"] = {"owner": "lab"}
    config["experiment"]["x_hint"] = "safe"

    errors = validate_config(config, mode="strict")
    assert errors == []


def test_strict_schema_rejects_invalid_recovery_retry() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["recovery"]["retry"]["max_attempts"] = 0

    errors = validate_config(config, mode="strict")
    assert any("max_attempts" in item for item in errors)


def test_strict_schema_rejects_ext_offset_safety_outside_glitch_range() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["safety"]["ext_offset_max"] = 2_000_000.0

    errors = validate_config(config, mode="strict")
    assert any("ext_offset" in item for item in errors)
