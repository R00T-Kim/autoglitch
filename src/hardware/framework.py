"""Transport-agnostic hardware discovery, binding, adapter registry, and locks."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from .mock import MockHardware
from .serial_async_hardware import AsyncSerialCommandHardware
from .serial_hardware import SerialCommandHardware
from .typed_serial_hardware import TypedSerialCommandHardware

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

        return sorted(results, key=lambda item: (-item.confidence, item.profile.adapter_id, item.binding.location))


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

    def save(self, binding: HardwareBinding, *, selected_from: str, candidates: list[DetectedHardware]) -> None:
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
_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


def load_profiles(profile_dirs: Iterable[Path] | None = None) -> list[HardwareProfile]:
    directories = [DEFAULT_PROFILE_DIR]
    if profile_dirs:
        directories.extend(profile_dirs)

    profiles: list[HardwareProfile] = []
    seen: set[str] = set()
    for directory in directories:
        if not directory.exists() or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(payload, dict):
                continue
            adapter_id = str(payload.get("adapter_id", "")).strip()
            if not adapter_id or adapter_id in seen:
                continue
            seen.add(adapter_id)
            profiles.append(
                HardwareProfile(
                    adapter_id=adapter_id,
                    display_name=str(payload.get("display_name", adapter_id)),
                    transport=str(payload.get("transport", "serial")),
                    protocol=str(payload.get("protocol", "legacy-text")),
                    supported_targets=tuple(str(item) for item in payload.get("supported_targets", ["*"])),
                    capabilities=tuple(str(item) for item in payload.get("capabilities", [])),
                    default_baudrate=int(payload.get("default_baudrate", 115200)),
                    default_timeout_s=float(payload.get("default_timeout_s", 0.25)),
                    max_confidence=float(payload.get("max_confidence", 0.99)),
                    metadata=dict(payload.get("metadata", {})),
                )
            )
    return profiles


def build_default_registry(profile_dirs: Iterable[Path] | None = None) -> HardwareRegistry:
    profiles = {profile.adapter_id: profile for profile in load_profiles(profile_dirs)}
    definitions = [
        HardwareAdapterDefinition(
            profile=profiles.get("mock-hardware", _fallback_mock_profile()),
            create=_create_mock_hardware,
            detect=_detect_mock_hardware,
            aliases=("mock", "simulation"),
        ),
        HardwareAdapterDefinition(
            profile=profiles.get("serial-json-hardware", _fallback_typed_profile()),
            create=_create_typed_serial_hardware,
            detect=_detect_typed_serial_hardware,
            aliases=("typed-serial", "json-serial", "auto-json"),
        ),
        HardwareAdapterDefinition(
            profile=profiles.get("serial-command-hardware", _fallback_legacy_serial_profile()),
            create=_create_legacy_serial_hardware,
            detect=_detect_legacy_serial_hardware,
            aliases=("serial", "legacy-serial"),
        ),
    ]
    return HardwareRegistry(definitions)


def binding_store_from_config(config: dict[str, Any], binding_file: str | None = None) -> HardwareBindingStore:
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    path = Path(binding_file or hw_cfg.get("binding_file") or DEFAULT_BINDING_FILE)
    return HardwareBindingStore(path)


def candidate_serial_ports(config: dict[str, Any], *, include: Iterable[str] = ()) -> list[str]:
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    discovery_cfg = hw_cfg.get("discovery", {}) if isinstance(hw_cfg.get("discovery", {}), dict) else {}
    target_cfg = hw_cfg.get("target", {}) if isinstance(hw_cfg.get("target", {}), dict) else {}

    ports: list[str] = []
    for value in include:
        if value:
            ports.append(str(value))

    configured = discovery_cfg.get("candidate_ports", [])
    if isinstance(configured, str):
        configured = [configured]
    if isinstance(configured, list):
        ports.extend(str(item) for item in configured if item)

    target_port = target_cfg.get("port")
    if target_port:
        ports.append(str(target_port))

    globs = discovery_cfg.get("port_globs", list(DEFAULT_PORT_GLOBS))
    if isinstance(globs, str):
        globs = [globs]
    for pattern in globs if isinstance(globs, list) else list(DEFAULT_PORT_GLOBS):
        for path in sorted(Path("/").glob(str(pattern).lstrip("/"))):
            ports.append(str(path))

    # Deduplicate preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for port in ports:
        if port in seen:
            continue
        seen.add(port)
        unique.append(port)
    return unique


def resolve_hardware(
    *,
    config: dict[str, Any],
    explicit_adapter: str | None,
    explicit_port: str | None,
    seed: int,
    registry: HardwareRegistry | None = None,
    binding_file: str | None = None,
) -> HardwareResolution:
    registry = registry or build_default_registry(_profile_dirs_from_config(config))
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    target_name = str(config.get("target", {}).get("name", hw_cfg.get("target", {}).get("type", "")))
    adapter_raw = hw_cfg.get("adapter")
    if str(adapter_raw or "").lower() in {"", "auto", "none"}:
        adapter_raw = hw_cfg.get("mode")
    explicit_requested = normalize_adapter_request(explicit_adapter)
    config_requested = normalize_adapter_request(adapter_raw)
    preferred_requested = normalize_adapter_request(hw_cfg.get("preferred_adapter"))
    requested = explicit_requested or config_requested or preferred_requested
    transport_filter = str(hw_cfg.get("transport", "auto"))
    store = binding_store_from_config(config, binding_file)

    if explicit_requested == "mock-hardware":
        binding = HardwareBinding(
            adapter_id="mock-hardware",
            profile="mock-hardware",
            transport="virtual",
            location="mock://local",
            target=target_name or None,
            metadata={"seed": seed},
        )
        _validate_required_capabilities(binding=binding, config=config, registry=registry)
        return HardwareResolution(selected=binding, candidates=[], source="explicit")

    local_binding = store.load() if store.path.exists() else None
    if explicit_requested is None and local_binding is not None:
        if explicit_port:
            local_binding.location = explicit_port
        _validate_required_capabilities(binding=local_binding, config=config, registry=registry)
        return HardwareResolution(selected=local_binding, candidates=[], source="local-binding")

    if explicit_port and requested in {None, "serial-command-hardware", "serial-json-hardware"}:
        detected = registry.detect(
            candidate_ports=[explicit_port],
            config=config,
            target_name=target_name,
            preferred_adapter=requested,
            transport_filter="serial",
        )
        unique = _unique_high_confidence_match(detected)
        if unique is not None:
            _validate_required_capabilities(binding=unique.binding, config=config, registry=registry)
            return HardwareResolution(selected=unique.binding, candidates=detected, source="explicit-port")
        if requested is not None:
            definition = registry.get(requested)
            if definition is None:
                raise HardwareResolutionError(f"unknown hardware adapter: {requested}")
            binding = HardwareBinding(
                adapter_id=definition.profile.adapter_id,
                profile=definition.profile.adapter_id,
                transport=definition.profile.transport,
                location=explicit_port,
                baudrate=_default_baudrate_for(config, definition.profile),
                timeout_s=_default_timeout_for(config, definition.profile),
                target=target_name or None,
            )
            _validate_required_capabilities(binding=binding, config=config, registry=registry)
            return HardwareResolution(selected=binding, candidates=detected, source="explicit-port")

    auto_detect = bool(hw_cfg.get("auto_detect", True))
    if requested is not None or auto_detect:
        detected = registry.detect(
            candidate_ports=candidate_serial_ports(
                config,
                include=[explicit_port] if explicit_port else [],
            ),
            config=config,
            target_name=target_name,
            preferred_adapter=requested,
            transport_filter=transport_filter,
        )
        unique = _unique_high_confidence_match(detected)
        if unique is not None:
            _validate_required_capabilities(binding=unique.binding, config=config, registry=registry)
            return HardwareResolution(selected=unique.binding, candidates=detected, source="auto-detect")
        if requested is not None and not detected:
            raise HardwareResolutionError(f"requested hardware adapter not detected: {requested}")
        if len(detected) > 1:
            rendered = ", ".join(
                f"{item.profile.adapter_id}@{item.binding.location}({item.confidence:.2f})" for item in detected[:5]
            )
            raise HardwareResolutionError(
                f"ambiguous hardware detection; multiple matches found: {rendered}"
            )

    if str(hw_cfg.get("mode", "mock")).lower() == "mock":
        binding = HardwareBinding(
            adapter_id="mock-hardware",
            profile="mock-hardware",
            transport="virtual",
            location="mock://fallback",
            target=target_name or None,
            metadata={"seed": seed},
        )
        _validate_required_capabilities(binding=binding, config=config, registry=registry)
        return HardwareResolution(selected=binding, candidates=[], source="fallback-mock")

    target_cfg = hw_cfg.get("target", {}) if isinstance(hw_cfg.get("target", {}), dict) else {}
    if str(hw_cfg.get("mode", "")).lower() == "serial" and target_cfg.get("port"):
        legacy_definition = registry.get("serial-command-hardware")
        if legacy_definition is None:
            raise HardwareResolutionError("legacy serial adapter profile is not registered")
        binding = HardwareBinding(
            adapter_id="serial-command-hardware",
            profile="serial-command-hardware",
            transport="serial",
            location=str(target_cfg["port"]),
            baudrate=_default_baudrate_for(config, legacy_definition.profile),
            timeout_s=_default_timeout_for(config, legacy_definition.profile),
            target=target_name or None,
        )
        _validate_required_capabilities(binding=binding, config=config, registry=registry)
        return HardwareResolution(selected=binding, candidates=[], source="legacy-config")

    raise HardwareResolutionError(
        "no supported hardware resolved. Run `detect-hardware` or `setup-hardware`, or pass --hardware/--serial-port explicitly."
    )


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


def detect_hardware(
    *,
    config: dict[str, Any],
    explicit_adapter: str | None = None,
    explicit_port: str | None = None,
    registry: HardwareRegistry | None = None,
) -> list[DetectedHardware]:
    registry = registry or build_default_registry(_profile_dirs_from_config(config))
    target_name = str(config.get("target", {}).get("name", ""))
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    transport_filter = str(hw_cfg.get("transport", "auto"))
    adapter_raw = hw_cfg.get("adapter")
    if str(adapter_raw or "").lower() in {"", "auto", "none"}:
        adapter_raw = hw_cfg.get("mode")
    config_requested = normalize_adapter_request(adapter_raw)
    preferred_requested = normalize_adapter_request(hw_cfg.get("preferred_adapter"))
    requested = normalize_adapter_request(explicit_adapter) or config_requested or preferred_requested
    detected = registry.detect(
        candidate_ports=candidate_serial_ports(config, include=[explicit_port] if explicit_port else []),
        config=config,
        target_name=target_name,
        preferred_adapter=requested,
        transport_filter=transport_filter,
    )
    return [
        candidate
        for candidate in detected
        if _candidate_supports_required_capabilities(candidate, config=config, registry=registry)
    ]


def doctor_hardware(
    *,
    config: dict[str, Any],
    explicit_adapter: str | None = None,
    explicit_port: str | None = None,
    binding_file: str | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    findings: list[HardwareDoctorFinding] = []
    candidates = detect_hardware(
        config=config,
        explicit_adapter=explicit_adapter,
        explicit_port=explicit_port,
    )
    store = binding_store_from_config(config, binding_file)
    binding = None
    selected_from = "none"
    try:
        resolution = resolve_hardware(
            config=config,
            explicit_adapter=explicit_adapter,
            explicit_port=explicit_port,
            seed=seed,
            binding_file=binding_file,
        )
        binding = resolution.selected
        selected_from = resolution.source
    except Exception as exc:
        findings.append(HardwareDoctorFinding("error", "resolution_failed", str(exc)))

    if binding is None and not candidates:
        findings.append(
            HardwareDoctorFinding(
                "error",
                "no_candidates",
                "No supported hardware candidates were detected on the current machine.",
            )
        )
    elif binding is None and len(candidates) > 1:
        findings.append(
            HardwareDoctorFinding(
                "warning",
                "ambiguous_candidates",
                "Multiple high-confidence hardware candidates were found; bind one explicitly with setup-hardware.",
            )
        )

    if not store.path.exists():
        findings.append(
            HardwareDoctorFinding(
                "info",
                "missing_local_binding",
                f"No local binding file exists at {store.path}; setup-hardware will create one.",
            )
        )

    status = "ok" if not any(item.severity == "error" for item in findings) else "degraded"
    return {
        "schema_version": 1,
        "status": status,
        "binding_file": str(store.path),
        "selected_from": selected_from,
        "selected_binding": binding.to_dict() if binding is not None else None,
        "candidates": [candidate.to_dict() for candidate in candidates],
        "findings": [item.to_dict() for item in findings],
    }


def _unique_high_confidence_match(candidates: list[DetectedHardware]) -> DetectedHardware | None:
    if not candidates:
        return None
    best = candidates[0]
    if best.confidence < 0.8:
        return None
    if len(candidates) == 1:
        return best
    second = candidates[1]
    if abs(best.confidence - second.confidence) < 0.05 and best.binding.location != second.binding.location:
        return None
    return best


def hardware_lock_path(
    binding: HardwareBinding | dict[str, Any] | None,
    *,
    lock_dir: Path = DEFAULT_LOCK_DIR,
) -> Path | None:
    if binding is None:
        return None
    if isinstance(binding, dict):
        adapter_id = str(binding.get("adapter_id", "")).strip()
        transport = str(binding.get("transport", "")).strip().lower()
        location = str(binding.get("location", "")).strip()
    else:
        adapter_id = binding.adapter_id
        transport = binding.transport.lower()
        location = binding.location
    if not adapter_id or not location or transport in {"", "virtual"}:
        return None
    digest = hashlib.sha256(f"{adapter_id}|{transport}|{location}".encode("utf-8")).hexdigest()[:16]
    return lock_dir / f"{adapter_id}-{digest}.lock"


@contextmanager
def hardware_binding_lock(
    binding: HardwareBinding | dict[str, Any] | None,
    *,
    timeout_s: float = 0.0,
    lock_dir: Path = DEFAULT_LOCK_DIR,
):
    lock_path = hardware_lock_path(binding, lock_dir=lock_dir)
    if lock_path is None:
        yield None
        return

    import fcntl

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = str(lock_path.resolve())
    with _PROCESS_LOCKS_GUARD:
        process_lock = _PROCESS_LOCKS.setdefault(lock_key, threading.Lock())

    if not process_lock.acquire(timeout=max(0.0, timeout_s)):
        raise HardwareResolutionError(f"hardware binding is already in use: {lock_path}")

    deadline = time.monotonic() + max(0.0, timeout_s)
    acquired = False
    try:
        with open(lock_path, "a+", encoding="utf-8") as handle:
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    handle.seek(0)
                    handle.truncate()
                    handle.write(f"pid={os.getpid()}\n")
                    handle.flush()
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise HardwareResolutionError(
                            f"hardware binding is already in use: {lock_path}"
                        ) from exc
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            try:
                yield lock_path
            finally:
                if acquired:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        process_lock.release()


def _create_mock_hardware(binding: HardwareBinding, _config: dict[str, Any], seed: int) -> MockHardware:
    effective_seed = int(binding.metadata.get("seed", seed))
    return MockHardware(seed=effective_seed)


def _create_legacy_serial_hardware(binding: HardwareBinding, config: dict[str, Any], seed: int) -> Any:  # noqa: ARG001
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    serial_cfg = hw_cfg.get("serial", {}) if isinstance(hw_cfg.get("serial", {}), dict) else {}
    target_cfg = hw_cfg.get("target", {}) if isinstance(hw_cfg.get("target", {}), dict) else {}
    timeout = binding.timeout_s or float(target_cfg.get("timeout", 1.0))
    command_template = str(
        hw_cfg.get(
            "serial_command_template",
            "GLITCH width={width:.3f} offset={offset:.3f} voltage={voltage:.3f} repeat={repeat:d} ext_offset={ext_offset:.3f}",
        )
    )
    reset_command = str(hw_cfg.get("reset_command", ""))
    trigger_command = str(hw_cfg.get("trigger_command", ""))
    io_mode = str(serial_cfg.get("io_mode", "sync")).lower()
    if io_mode == "async":
        return AsyncSerialCommandHardware(
            port=binding.location,
            baudrate=int(binding.baudrate or target_cfg.get("baudrate", 115200)),
            timeout=float(timeout),
            command_template=command_template,
            reset_command=reset_command,
            trigger_command=trigger_command,
            keep_open=bool(serial_cfg.get("keep_open", True)),
            reconnect_attempts=int(serial_cfg.get("reconnect_attempts", 2)),
            reconnect_backoff_s=float(serial_cfg.get("reconnect_backoff_s", 0.05)),
        )
    return SerialCommandHardware(
        port=binding.location,
        baudrate=int(binding.baudrate or target_cfg.get("baudrate", 115200)),
        timeout=float(timeout),
        command_template=command_template,
        reset_command=reset_command,
        trigger_command=trigger_command,
    )


def _create_typed_serial_hardware(binding: HardwareBinding, config: dict[str, Any], _seed: int) -> TypedSerialCommandHardware:
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    target_cfg = hw_cfg.get("target", {}) if isinstance(hw_cfg.get("target", {}), dict) else {}
    return TypedSerialCommandHardware(
        port=binding.location,
        baudrate=int(binding.baudrate or target_cfg.get("baudrate", 115200)),
        timeout=float(binding.timeout_s or target_cfg.get("timeout", 1.0)),
    )


def _detect_mock_hardware(
    profile: HardwareProfile,
    _candidate_ports: list[str],
    config: dict[str, Any],
) -> list[DetectedHardware]:
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    adapter_raw = hw_cfg.get("adapter")
    if str(adapter_raw or "").lower() in {"", "auto", "none"}:
        adapter_raw = hw_cfg.get("mode")
    requested = normalize_adapter_request(adapter_raw)
    if requested != "mock-hardware" and str(hw_cfg.get("mode", "")).lower() != "mock":
        return []
    binding = HardwareBinding(
        adapter_id=profile.adapter_id,
        profile=profile.adapter_id,
        transport=profile.transport,
        location="mock://local",
        target=str(config.get("target", {}).get("name", "")) or None,
        metadata={"seed": int(config.get("experiment", {}).get("seed", 42))},
    )
    return [
        DetectedHardware(
            profile=profile,
            binding=binding,
            confidence=profile.max_confidence,
            reason="simulation_requested",
            metadata={"simulated": True},
        )
    ]


def _detect_typed_serial_hardware(
    profile: HardwareProfile,
    candidate_ports: list[str],
    config: dict[str, Any],
) -> list[DetectedHardware]:
    results: list[DetectedHardware] = []
    timeout = _default_timeout_for(config, profile)
    baudrate = _default_baudrate_for(config, profile)
    for port in candidate_ports:
        probe = TypedSerialCommandHardware.probe(port=port, baudrate=baudrate, timeout=timeout)
        if probe is None:
            continue
        binding = HardwareBinding(
            adapter_id=profile.adapter_id,
            profile=profile.adapter_id,
            transport=profile.transport,
            location=port,
            baudrate=baudrate,
            timeout_s=timeout,
            target=str(config.get("target", {}).get("name", "")) or None,
            metadata={k: v for k, v in probe.items() if k not in {"confidence", "reason"}},
        )
        results.append(
            DetectedHardware(
                profile=profile,
                binding=binding,
                confidence=float(probe.get("confidence", profile.max_confidence)),
                reason=str(probe.get("reason", "typed_handshake_ok")),
                metadata=dict(probe),
            )
        )
    return results


def _detect_legacy_serial_hardware(
    profile: HardwareProfile,
    candidate_ports: list[str],
    config: dict[str, Any],
) -> list[DetectedHardware]:
    results: list[DetectedHardware] = []
    timeout = _default_timeout_for(config, profile)
    baudrate = _default_baudrate_for(config, profile)
    for port in candidate_ports:
        probe = SerialCommandHardware.probe(port=port, baudrate=baudrate, timeout=timeout)
        if probe is None:
            continue
        binding = HardwareBinding(
            adapter_id=profile.adapter_id,
            profile=profile.adapter_id,
            transport=profile.transport,
            location=port,
            baudrate=baudrate,
            timeout_s=timeout,
            target=str(config.get("target", {}).get("name", "")) or None,
            metadata={k: v for k, v in probe.items() if k not in {"confidence", "reason"}},
        )
        results.append(
            DetectedHardware(
                profile=profile,
                binding=binding,
                confidence=float(probe.get("confidence", min(0.9, profile.max_confidence))),
                reason=str(probe.get("reason", "legacy_handshake_ok")),
                metadata=dict(probe),
            )
        )
    return results


def _default_baudrate_for(config: dict[str, Any], profile: HardwareProfile) -> int:
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    target_cfg = hw_cfg.get("target", {}) if isinstance(hw_cfg.get("target", {}), dict) else {}
    return int(target_cfg.get("baudrate", profile.default_baudrate))


def _default_timeout_for(config: dict[str, Any], profile: HardwareProfile) -> float:
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    target_cfg = hw_cfg.get("target", {}) if isinstance(hw_cfg.get("target", {}), dict) else {}
    discovery_cfg = hw_cfg.get("discovery", {}) if isinstance(hw_cfg.get("discovery", {}), dict) else {}
    probe_timeout = discovery_cfg.get("probe_timeout_s")
    if probe_timeout is not None:
        return float(probe_timeout)
    return float(target_cfg.get("timeout", profile.default_timeout_s))


def _profile_dirs_from_config(config: dict[str, Any]) -> list[Path]:
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    directories = hw_cfg.get("profile_dirs", [])
    if isinstance(directories, str):
        directories = [directories]
    if not isinstance(directories, list):
        return []
    return [Path(str(item)) for item in directories if str(item)]


def _fallback_mock_profile() -> HardwareProfile:
    return HardwareProfile(
        adapter_id="mock-hardware",
        display_name="Mock Hardware",
        transport="virtual",
        protocol="simulation",
        capabilities=("simulation", "glitch.execute"),
    )


def _fallback_typed_profile() -> HardwareProfile:
    return HardwareProfile(
        adapter_id="serial-json-hardware",
        display_name="Typed Serial Bridge",
        transport="serial",
        protocol="autoglitch.v1",
        capabilities=("glitch.execute", "target.reset", "target.trigger", "healthcheck"),
    )


def _fallback_legacy_serial_profile() -> HardwareProfile:
    return HardwareProfile(
        adapter_id="serial-command-hardware",
        display_name="Legacy Serial Text Bridge",
        transport="serial",
        protocol="legacy-text",
        capabilities=("glitch.execute", "target.reset", "target.trigger"),
        max_confidence=0.9,
    )


def _required_capabilities(config: dict[str, Any]) -> set[str]:
    hw_cfg = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
    values = hw_cfg.get("required_capabilities", [])
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return set()
    return {str(item).strip() for item in values if str(item).strip()}


def _candidate_capabilities(
    candidate: DetectedHardware,
    *,
    registry: HardwareRegistry,
) -> set[str]:
    definition = registry.get(candidate.binding.adapter_id)
    capabilities = set(definition.profile.capabilities) if definition is not None else set()
    metadata_caps = candidate.metadata.get("capabilities", [])
    if isinstance(metadata_caps, list):
        capabilities.update(str(item).strip() for item in metadata_caps if str(item).strip())
    binding_caps = candidate.binding.metadata.get("capabilities", [])
    if isinstance(binding_caps, list):
        capabilities.update(str(item).strip() for item in binding_caps if str(item).strip())
    return capabilities


def _binding_capabilities(
    binding: HardwareBinding,
    *,
    registry: HardwareRegistry,
) -> set[str]:
    definition = registry.get(binding.adapter_id)
    capabilities = set(definition.profile.capabilities) if definition is not None else set()
    metadata_caps = binding.metadata.get("capabilities", [])
    if isinstance(metadata_caps, list):
        capabilities.update(str(item).strip() for item in metadata_caps if str(item).strip())
    return capabilities


def _candidate_supports_required_capabilities(
    candidate: DetectedHardware,
    *,
    config: dict[str, Any],
    registry: HardwareRegistry,
) -> bool:
    required = _required_capabilities(config)
    if not required:
        return True
    return required.issubset(_candidate_capabilities(candidate, registry=registry))


def _validate_required_capabilities(
    *,
    binding: HardwareBinding,
    config: dict[str, Any],
    registry: HardwareRegistry,
) -> None:
    required = _required_capabilities(config)
    if not required:
        return
    available = _binding_capabilities(binding, registry=registry)
    missing = sorted(required - available)
    if missing:
        raise HardwareResolutionError(
            f"resolved hardware {binding.adapter_id} is missing required capabilities: {', '.join(missing)}"
        )


__all__ = [
    "DEFAULT_BINDING_FILE",
    "DetectedHardware",
    "HardwareBinding",
    "HardwareBindingStore",
    "HardwareDoctorFinding",
    "HardwareProfile",
    "HardwareRegistry",
    "HardwareResolution",
    "HardwareResolutionError",
    "binding_store_from_config",
    "build_default_registry",
    "candidate_serial_ports",
    "detect_hardware",
    "doctor_hardware",
    "hardware_binding_lock",
    "hardware_lock_path",
    "normalize_adapter_request",
    "resolve_hardware",
]
