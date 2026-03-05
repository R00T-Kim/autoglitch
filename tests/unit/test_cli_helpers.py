from __future__ import annotations

import argparse
from pathlib import Path

from src.cli import (
    _aggregate_rerun_results,
    _deep_merge,
    _load_config,
    _load_run_config,
)


def test_deep_merge_overrides_nested_values() -> None:
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    overlay = {"nested": {"y": 99, "z": 3}}

    merged = _deep_merge(base, overlay)

    assert merged["a"] == 1
    assert merged["nested"]["x"] == 1
    assert merged["nested"]["y"] == 99
    assert merged["nested"]["z"] == 3


def test_load_config_merges_target_profile() -> None:
    config = _load_config(Path("configs/default.yaml"), "stm32f3")

    assert "target" in config
    assert config["target"]["name"] == "STM32F303"
    assert config["glitch"]["parameters"]["width"]["max"] == 50.0


def test_aggregate_rerun_results_computes_stable_ratio() -> None:
    runs = [
        {"success_rate": 0.4, "primitive_repro_rate": 0.5, "time_to_first_primitive": 3},
        {"success_rate": 0.2, "primitive_repro_rate": 0.1, "time_to_first_primitive": None},
        {"success_rate": 0.8, "primitive_repro_rate": 0.35, "time_to_first_primitive": 2},
    ]

    aggregate = _aggregate_rerun_results(runs, success_threshold=0.3)

    assert aggregate["stable_runs"] == 2
    assert aggregate["stable_run_ratio"] == 2 / 3
    assert aggregate["time_to_first_primitive_best"] == 2


def test_load_run_config_applies_template_overrides(tmp_path) -> None:
    template = tmp_path / "template.yaml"
    template.write_text(
        "\n".join(
            [
                "name: test_template",
                "base_config: configs/default.yaml",
                "target: esp32",
                "experiment:",
                "  rerun_count: 3",
                "optimizer:",
                "  bo:",
                "    backend: heuristic",
            ]
        )
    )

    args = argparse.Namespace(config="configs/default.yaml", target="stm32f3", template=str(template))
    config, template_name = _load_run_config(args)

    assert template_name == "test_template"
    assert config["target"]["name"] == "ESP32"
    assert config["experiment"]["rerun_count"] == 3
    assert config["optimizer"]["bo"]["backend"] == "heuristic"
