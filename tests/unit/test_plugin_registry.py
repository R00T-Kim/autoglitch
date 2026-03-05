from __future__ import annotations

from pathlib import Path

from src.plugins import PluginRegistry


def test_default_registry_loads_builtin_manifests() -> None:
    registry = PluginRegistry.load_default()
    plugins = registry.list()

    assert plugins
    assert registry.get("mock-hardware") is not None


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
