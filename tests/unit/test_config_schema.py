from __future__ import annotations

import copy
from pathlib import Path

import yaml

from src.config import validate_config
from src.config.schema import parse_autoglitch_config
from src.cli import _load_config


def _merged_default() -> dict:
    return _load_config(Path("configs/default.yaml"), "stm32f3")


def test_strict_schema_accepts_default_merged_config() -> None:
    config = _merged_default()
    errors = validate_config(config, mode="strict")
    assert errors == []
    parsed = parse_autoglitch_config(config)
    assert parsed.target.name == "STM32F303"


def test_strict_schema_rejects_string_numeric_values() -> None:
    config = _merged_default()
    config = copy.deepcopy(config)
    config["experiment"]["seed"] = "42"

    errors = validate_config(config, mode="strict")
    assert any("experiment.seed" in item for item in errors)


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
