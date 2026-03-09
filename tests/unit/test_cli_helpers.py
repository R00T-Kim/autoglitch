from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.cli import (
    _aggregate_rerun_results,
    _deep_merge,
    _load_config,
    _load_run_config,
    _resolve_effective_hardware_mode,
    _run_single_campaign,
)
from src.plugins import PluginRegistry


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

    args = argparse.Namespace(
        config="configs/default.yaml", target="stm32f3", template=str(template)
    )
    config, template_name = _load_run_config(args)

    assert template_name == "test_template"
    assert config["target"]["name"] == "ESP32"
    assert config["experiment"]["rerun_count"] == 3
    assert config["optimizer"]["bo"]["backend"] == "heuristic"


def test_resolve_effective_hardware_mode_uses_template_when_cli_hardware_missing(tmp_path) -> None:
    template = tmp_path / "serial_template.yaml"
    template.write_text(
        "\n".join(
            [
                "name: serial_template",
                "base_config: configs/default.yaml",
                "target: stm32f3",
                "hardware:",
                "  mode: serial",
            ]
        ),
        encoding="utf-8",
    )

    args = argparse.Namespace(
        config="configs/default.yaml",
        target="stm32f3",
        template=str(template),
        hardware=None,
    )

    assert _resolve_effective_hardware_mode(args) == "serial"


def test_run_single_campaign_disconnects_hardware_and_ends_tracker_on_failure(
    monkeypatch, tmp_path
) -> None:
    tracker_calls: list[str] = []

    class _Tracker:
        def start_run(self, **_kwargs) -> None:
            tracker_calls.append("start")

        def end_run(self, status: str = "FINISHED") -> None:
            tracker_calls.append(f"end:{status}")

        def snapshot(self) -> dict:
            return {"enabled": False}

        def log_metrics(self, *_args, **_kwargs) -> None:
            raise AssertionError("log_metrics should not be called on failure")

        def log_artifact(self, *_args, **_kwargs) -> None:
            raise AssertionError("log_artifact should not be called on failure")

    class _Hardware:
        def __init__(self) -> None:
            self.disconnected = False

        def disconnect(self) -> None:
            self.disconnected = True

    hardware = _Hardware()

    class _FailingOrchestrator:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def run_campaign(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "src.cli._create_optimizer",
        lambda *args, **kwargs: SimpleNamespace(backend_in_use="heuristic"),
    )
    monkeypatch.setattr("src.cli._create_mlflow_tracker", lambda _config: _Tracker())
    monkeypatch.setattr("src.cli._create_hardware", lambda **_kwargs: hardware)
    monkeypatch.setattr("src.cli.ExperimentOrchestrator", _FailingOrchestrator)

    args = argparse.Namespace(
        optimizer="bayesian",
        bo_backend="heuristic",
        rl_backend=None,
        enable_llm=False,
        ai_mode="off",
        policy_file=None,
        target_primitive=None,
        hardware="mock",
        serial_port=None,
        serial_timeout=None,
        binding_file=None,
        serial_io=None,
        run_tag="unit",
    )

    with pytest.raises(RuntimeError, match="boom"):
        _run_single_campaign(
            run_config={
                "experiment": {"seed": 123},
                "glitch": {"parameters": {"width": {}, "offset": {}, "voltage": {}, "repeat": {}}},
                "optimizer": {"type": "bayesian", "bo": {}},
                "logging": {},
                "target": {"name": "STM32F303"},
                "hardware": {"mode": "mock"},
                "recovery": {"retry": {}, "circuit_breaker": {}},
            },
            args=args,
            run_seed=123,
            run_id="cleanup-test",
            trials=2,
            target_primitive=None,
            plugin_registry=PluginRegistry.load_default(),
        )

    assert hardware.disconnected is True
    assert tracker_calls == ["start", "end:FAILED"]


def test_run_single_campaign_instantiates_configured_component_plugins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = tmp_path / "runtime_plugins"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "components.py").write_text(
        "\n".join(
            [
                "class CustomObserver:",
                "    pass",
                "",
                "class CustomClassifier:",
                "    pass",
                "",
                "class CustomMapper:",
                "    pass",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    manifests = {
        "custom-observer.yaml": ("custom-observer", "observer", "CustomObserver"),
        "custom-classifier.yaml": ("custom-classifier", "classifier", "CustomClassifier"),
        "custom-mapper.yaml": ("custom-mapper", "mapper", "CustomMapper"),
    }
    for filename, (name, kind, class_name) in manifests.items():
        (tmp_path / filename).write_text(
            "\n".join(
                [
                    f"name: {name}",
                    f"kind: {kind}",
                    "version: 0.1.0",
                    "module: runtime_plugins.components",
                    f"class_name: {class_name}",
                    "supported_targets:",
                    "  - '*'",
                ]
            ),
            encoding="utf-8",
        )

    class _Tracker:
        def start_run(self, **_kwargs) -> None:
            return None

        def end_run(self, status: str = "FINISHED") -> None:  # noqa: ARG002
            return None

        def snapshot(self) -> dict:
            return {"enabled": False}

        def log_metrics(self, *_args, **_kwargs) -> None:
            return None

        def log_artifact(self, *_args, **_kwargs) -> None:
            return None

    class _Hardware:
        def disconnect(self) -> None:
            return None

    captured: dict[str, object] = {}

    class _Orchestrator:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            captured.update(kwargs)

        def run_campaign(self, *args, **kwargs):  # noqa: ANN002, ANN003
            from src.types import CampaignResult

            return CampaignResult(
                campaign_id="component-test",
                config=kwargs.get("config", captured.get("config", {}))
                or captured.get("config", {}),
            )

    monkeypatch.setattr(
        "src.cli_execution.ExperimentLogger",
        lambda run_id: __import__(
            "src.logging_viz", fromlist=["ExperimentLogger"]
        ).ExperimentLogger(
            output_dir=str(tmp_path / "logs"),
            run_id=run_id,
        ),
    )
    monkeypatch.setattr(
        "src.cli._create_optimizer",
        lambda *args, **kwargs: SimpleNamespace(backend_in_use="heuristic"),
    )
    monkeypatch.setattr("src.cli._create_mlflow_tracker", lambda _config: _Tracker())
    monkeypatch.setattr("src.cli._create_hardware", lambda **_kwargs: _Hardware())
    monkeypatch.setattr("src.cli.ExperimentOrchestrator", _Orchestrator)

    args = argparse.Namespace(
        optimizer="bayesian",
        bo_backend="heuristic",
        rl_backend=None,
        enable_llm=False,
        ai_mode="off",
        policy_file=None,
        target_primitive=None,
        hardware="mock",
        serial_port=None,
        serial_timeout=None,
        binding_file=None,
        serial_io=None,
        run_tag="unit",
    )
    plugin_registry = PluginRegistry.load_default(extra_dirs=[tmp_path])

    summary = _run_single_campaign(
        run_config={
            "experiment": {"seed": 123},
            "glitch": {"parameters": {"width": {}, "offset": {}, "voltage": {}, "repeat": {}}},
            "optimizer": {"type": "bayesian", "bo": {}},
            "logging": {},
            "target": {"name": "STM32F303"},
            "hardware": {"mode": "mock", "target": {"type": "stm32f3"}},
            "components": {
                "observer": "custom-observer",
                "classifier": "custom-classifier",
                "mapper": "custom-mapper",
            },
            "recovery": {"retry": {}, "circuit_breaker": {}},
        },
        args=args,
        run_seed=123,
        run_id="component-test",
        trials=2,
        target_primitive=None,
        plugin_registry=plugin_registry,
    )

    assert captured["observer"].__class__.__name__ == "CustomObserver"
    assert captured["classifier"].__class__.__name__ == "CustomClassifier"
    assert captured["mapper"].__class__.__name__ == "CustomMapper"
    assert summary["component_plugins"] == {
        "observer": "custom-observer",
        "classifier": "custom-classifier",
        "mapper": "custom-mapper",
    }
