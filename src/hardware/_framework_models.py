"""Core hardware registry, binding, and profile models."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ProfileFactory = Callable[["HardwareBinding", dict[str, Any], int], Any]
ProbeFn = Callable[["HardwareProfile", list[str], dict[str, Any]], list["DetectedHardware"]]


@dataclass(frozen=True)
class HardwareProfile:
    """Official supported hardware profile."""

    adapter_id: str
    display_name: str
    transport: str
    protocol: str
    supported_targets: tuple[str, ...] = ("*",)
    capabilities: tuple[str, ...] = ()
    default_baudrate: int = 115200
    default_timeout_s: float = 0.25
    max_confidence: float = 0.99
    metadata: dict[str, Any] = field(default_factory=dict)

    def supports_target(self, target_name: str) -> bool:
        if not target_name:
            return True
        lowered = target_name.lower()
        return "*" in self.supported_targets or lowered in {
            item.lower() for item in self.supported_targets
        }


@dataclass
class HardwareBinding:
    """Local machine binding for a selected hardware adapter."""

    adapter_id: str
    profile: str
    transport: str
    location: str
    baudrate: int | None = None
    timeout_s: float | None = None
    target: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = 1
        return payload


@dataclass(frozen=True)
class DetectedHardware:
    """Discovery candidate emitted during probing."""

    profile: HardwareProfile
    binding: HardwareBinding
    confidence: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.profile.adapter_id,
            "profile": self.profile.display_name,
            "transport": self.profile.transport,
            "protocol": self.profile.protocol,
            "confidence": float(self.confidence),
            "reason": self.reason,
            "binding": self.binding.to_dict(),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class HardwareDoctorFinding:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class HardwareResolution:
    """Resolved adapter binding with supporting candidates."""

    selected: HardwareBinding
    candidates: list[DetectedHardware] = field(default_factory=list)
    source: str = "explicit"


@dataclass(frozen=True)
class HardwareAdapterDefinition:
    profile: HardwareProfile
    create: ProfileFactory
    detect: ProbeFn
    aliases: tuple[str, ...] = ()


class HardwareRegistry:
    """Runtime registry for hardware adapters and official profiles."""

    def __init__(self, definitions: Iterable[HardwareAdapterDefinition] | None = None):
        self._definitions: dict[str, HardwareAdapterDefinition] = {}
        self._aliases: dict[str, str] = {}
        if definitions:
            for definition in definitions:
                self.register(definition)

    def register(self, definition: HardwareAdapterDefinition) -> None:
        adapter_id = definition.profile.adapter_id
        if adapter_id in self._definitions:
            raise ValueError(f"duplicate hardware adapter id: {adapter_id}")
        self._definitions[adapter_id] = definition
        self._aliases[adapter_id] = adapter_id
        for alias in definition.aliases:
            alias_key = alias.lower()
            existing = self._aliases.get(alias_key)
            if existing is not None and existing != adapter_id:
                raise ValueError(f"duplicate hardware adapter alias: {alias}")
            self._aliases[alias_key] = adapter_id

    def adapter_ids(self) -> list[str]:
        return sorted(self._definitions.keys())

    def profiles(self) -> list[HardwareProfile]:
        return [definition.profile for definition in self._definitions.values()]

    def get(self, adapter_id_or_alias: str) -> HardwareAdapterDefinition | None:
        if not adapter_id_or_alias:
            return None
        adapter_id = self._aliases.get(adapter_id_or_alias.lower())
        if adapter_id is None:
            return None
        return self._definitions.get(adapter_id)

    def create(self, binding: HardwareBinding, config: dict[str, Any], seed: int) -> Any:
        definition = self.get(binding.adapter_id)
        if definition is None:
            raise RuntimeError(f"unknown hardware adapter: {binding.adapter_id}")
        return definition.create(binding, config, seed)

    def detect(
        self,
        *,
        candidate_ports: list[str],
        config: dict[str, Any],
        target_name: str,
        preferred_adapter: str | None = None,
        transport_filter: str | None = None,
    ) -> list[DetectedHardware]:
        preferred = self.get(preferred_adapter) if preferred_adapter else None
        definitions = [preferred] if preferred is not None else list(self._definitions.values())
        if preferred is None:
            definitions = list(self._definitions.values())

        results: list[DetectedHardware] = []
        for definition in definitions:
            if definition is None:
                continue
            profile = definition.profile
            if not profile.supports_target(target_name):
                continue
            if transport_filter and transport_filter not in {"auto", profile.transport}:
                continue
            results.extend(definition.detect(profile, candidate_ports, config))

        return sorted(
            results,
            key=lambda item: (-item.confidence, item.profile.adapter_id, item.binding.location),
        )


class HardwareResolutionError(RuntimeError):
    """Raised when hardware cannot be resolved safely."""


class HardwareBindingStore:
    """Local binding file loader/writer."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> HardwareBinding | None:
        if not self.path.exists():
            return None
        payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise RuntimeError(f"invalid hardware binding file: {self.path}")
        binding = payload.get("binding", payload)
        if not isinstance(binding, dict):
            raise RuntimeError(f"invalid binding payload: {self.path}")
        return HardwareBinding(
            adapter_id=str(binding["adapter_id"]),
            profile=str(binding.get("profile", binding["adapter_id"])),
            transport=str(binding.get("transport", "serial")),
            location=str(binding.get("location", "")),
            baudrate=int(binding["baudrate"]) if binding.get("baudrate") is not None else None,
            timeout_s=float(binding["timeout_s"]) if binding.get("timeout_s") is not None else None,
            target=str(binding["target"]) if binding.get("target") is not None else None,
            metadata=dict(binding.get("metadata", {})),
        )

    def save(
        self, binding: HardwareBinding, *, selected_from: str, candidates: list[DetectedHardware]
    ) -> None:
        payload = {
            "schema_version": 1,
            "selected_from": selected_from,
            "binding": binding.to_dict(),
            "candidates": [candidate.to_dict() for candidate in candidates],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


DEFAULT_BINDING_FILE = Path("configs/local/hardware.yaml")
DEFAULT_PROFILE_DIR = Path(__file__).resolve().parents[2] / "configs" / "hardware_profiles"
DEFAULT_LOCK_DIR = Path("configs/local/locks")
DEFAULT_PORT_GLOBS = (
    "/dev/ttyUSB*",
    "/dev/ttyACM*",
    "/dev/tty.usbserial*",
    "/dev/tty.usbmodem*",
    "/dev/cu.usbserial*",
    "/dev/cu.usbmodem*",
)


def load_profiles(profile_dirs: Iterable[Path] | None = None) -> list[HardwareProfile]:
    directories = [DEFAULT_PROFILE_DIR]
    if profile_dirs:
        directories.extend(profile_dirs)

    profiles_by_id: dict[str, HardwareProfile] = {}
    for directory in directories:
        if not directory.exists() or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(payload, dict):
                continue
            adapter_id = str(payload.get("adapter_id", "")).strip()
            if not adapter_id:
                continue
            previous = profiles_by_id.get(adapter_id)
            metadata = dict(previous.metadata) if previous is not None else {}
            metadata.update(dict(payload.get("metadata", {})))
            profiles_by_id[adapter_id] = HardwareProfile(
                adapter_id=adapter_id,
                display_name=str(
                    payload.get(
                        "display_name",
                        previous.display_name if previous is not None else adapter_id,
                    )
                ),
                transport=str(
                    payload.get(
                        "transport",
                        previous.transport if previous is not None else "serial",
                    )
                ),
                protocol=str(
                    payload.get(
                        "protocol",
                        previous.protocol if previous is not None else "legacy-text",
                    )
                ),
                supported_targets=tuple(
                    str(item)
                    for item in payload.get(
                        "supported_targets",
                        previous.supported_targets if previous is not None else ["*"],
                    )
                ),
                capabilities=tuple(
                    str(item)
                    for item in payload.get(
                        "capabilities",
                        previous.capabilities if previous is not None else [],
                    )
                ),
                default_baudrate=int(
                    payload.get(
                        "default_baudrate",
                        previous.default_baudrate if previous is not None else 115200,
                    )
                ),
                default_timeout_s=float(
                    payload.get(
                        "default_timeout_s",
                        previous.default_timeout_s if previous is not None else 0.25,
                    )
                ),
                max_confidence=float(
                    payload.get(
                        "max_confidence",
                        previous.max_confidence if previous is not None else 0.99,
                    )
                ),
                metadata=metadata,
            )
    return list(profiles_by_id.values())


def binding_store_from_config(
    config: dict[str, Any], binding_file: str | None = None
) -> HardwareBindingStore:
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    path = Path(binding_file or hw_cfg.get("binding_file") or DEFAULT_BINDING_FILE)
    return HardwareBindingStore(path)


def normalize_adapter_request(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized or normalized == "auto":
        return None
    aliases = {
        "mock": "mock-hardware",
        "simulation": "mock-hardware",
        "serial": "serial-command-hardware",
        "legacy-serial": "serial-command-hardware",
        "typed-serial": "serial-json-hardware",
        "json-serial": "serial-json-hardware",
    }
    return aliases.get(normalized, normalized)
