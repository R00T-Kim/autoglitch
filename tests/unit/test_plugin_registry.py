from __future__ import annotations

from pathlib import Path

import pytest

from src.plugins import PluginRegistry


def test_default_registry_loads_builtin_manifests() -> None:
    registry = PluginRegistry.load_default()
    plugins = registry.list()

    assert plugins
    assert registry.get("mock-hardware") is not None
    assert registry.get("serial-json-hardware") is not None


def test_registry_loads_extra_manifest_directory(tmp_path: Path) -> None:
    manifest = tmp_path / "custom-observer.yaml"
    manifest.write_text(
        "\n".join(
            [
                "name: custom-observer",
                "kind: observer",
                "version: 0.1.0",
                "module: custom.module",
                "class_name: CustomObserver",
            ]
        )
    )

    registry = PluginRegistry.load_default(extra_dirs=[tmp_path])
    plugin = registry.get("custom-observer")

    assert plugin is not None
    assert plugin.kind == "observer"
    assert plugin.module == "custom.module"


def test_registry_rejects_duplicate_plugin_names(tmp_path: Path) -> None:
    manifest = tmp_path / "mock-hardware.yaml"
    manifest.write_text(
        "\n".join(
            [
                "name: mock-hardware",
                "kind: hardware",
                "version: 9.9.9",
                "module: custom.module",
                "class_name: CustomHardware",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate plugin manifest name"):
        PluginRegistry.load_default(extra_dirs=[tmp_path])
