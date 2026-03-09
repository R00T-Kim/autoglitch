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


def test_registry_can_instantiate_plugin_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "custom"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "module.py").write_text(
        "\n".join(
            [
                "class CustomObserver:",
                "    def __init__(self) -> None:",
                "        self.loaded = True",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

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
        ),
        encoding="utf-8",
    )

    registry = PluginRegistry.load_default(extra_dirs=[tmp_path])
    instance = registry.instantiate("custom-observer", kind="observer")

    assert instance.__class__.__name__ == "CustomObserver"
    assert instance.loaded is True


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
