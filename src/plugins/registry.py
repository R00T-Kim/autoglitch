"""Plugin registry and manifest loader."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml


@dataclass(frozen=True)
class PluginManifest:
    name: str
    kind: str
    version: str
    module: str
    class_name: str
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    supported_targets: List[str] = field(default_factory=list)
    limits: Dict[str, Any] = field(default_factory=dict)
    source: str = "builtin"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PluginRegistry:
    """Registry that discovers plugin manifests from local directories."""

    def __init__(self, manifests: Optional[Iterable[PluginManifest]] = None):
        self._plugins: Dict[str, PluginManifest] = {}
        if manifests:
            for manifest in manifests:
                self.register(manifest)

    def register(self, manifest: PluginManifest) -> None:
        self._plugins[manifest.name] = manifest

    def list(self, kind: str | None = None) -> List[PluginManifest]:
        manifests = list(self._plugins.values())
        if kind is None:
            return sorted(manifests, key=lambda item: (item.kind, item.name))
        return sorted((item for item in manifests if item.kind == kind), key=lambda item: item.name)

    def get(self, name: str) -> Optional[PluginManifest]:
        return self._plugins.get(name)

    def snapshot(self) -> List[Dict[str, Any]]:
        return [manifest.to_dict() for manifest in self.list()]

    @classmethod
    def load_default(cls, extra_dirs: Optional[Iterable[Path]] = None) -> "PluginRegistry":
        registry = cls()
        for manifest_path in _default_manifest_paths(extra_dirs):
            manifest = _load_manifest(manifest_path)
            registry.register(manifest)
        return registry



def _default_manifest_paths(extra_dirs: Optional[Iterable[Path]]) -> List[Path]:
    manifests_dir = Path(__file__).resolve().parent / "manifests"
    manifest_paths = sorted(manifests_dir.glob("*.yaml"))

    if extra_dirs:
        for directory in extra_dirs:
            if not directory.exists() or not directory.is_dir():
                continue
            manifest_paths.extend(sorted(directory.glob("*.yaml")))

    # de-duplicate while preserving order
    seen: set[Path] = set()
    unique_paths: List[Path] = []
    for path in manifest_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)

    return unique_paths



def _load_manifest(path: Path) -> PluginManifest:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    required = ["name", "kind", "version", "module", "class_name"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"invalid plugin manifest {path}: missing {', '.join(missing)}")

    return PluginManifest(
        name=str(payload["name"]),
        kind=str(payload["kind"]),
        version=str(payload["version"]),
        module=str(payload["module"]),
        class_name=str(payload["class_name"]),
        description=str(payload.get("description", "")),
        capabilities=[str(item) for item in payload.get("capabilities", [])],
        supported_targets=[str(item) for item in payload.get("supported_targets", [])],
        limits=dict(payload.get("limits", {})),
        source=str(path),
    )
