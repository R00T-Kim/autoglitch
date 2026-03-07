"""Hardware resolution and discovery filtering helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ._framework_adapters import (
    _default_baudrate_for,
    _default_timeout_for,
    _profile_dirs_from_config,
    build_default_registry,
)
from ._framework_capabilities import (
    candidate_supports_required_capabilities,
    validate_required_capabilities,
)
from ._framework_models import (
    DEFAULT_PORT_GLOBS,
    DetectedHardware,
    HardwareBinding,
    HardwareRegistry,
    HardwareResolution,
    HardwareResolutionError,
    binding_store_from_config,
    normalize_adapter_request,
)


def candidate_serial_ports(config: dict[str, Any], *, include: list[str] | tuple[str, ...] = ()) -> list[str]:
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
        validate_required_capabilities(binding=binding, config=config, registry=registry)
        return HardwareResolution(selected=binding, candidates=[], source="explicit")

    local_binding = store.load() if store.path.exists() else None
    if explicit_requested is None and local_binding is not None:
        if explicit_port:
            local_binding.location = explicit_port
        validate_required_capabilities(binding=local_binding, config=config, registry=registry)
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
            validate_required_capabilities(binding=unique.binding, config=config, registry=registry)
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
            validate_required_capabilities(binding=binding, config=config, registry=registry)
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
            validate_required_capabilities(binding=unique.binding, config=config, registry=registry)
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
        validate_required_capabilities(binding=binding, config=config, registry=registry)
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
        validate_required_capabilities(binding=binding, config=config, registry=registry)
        return HardwareResolution(selected=binding, candidates=[], source="legacy-config")

    raise HardwareResolutionError(
        "no supported hardware resolved. Run `detect-hardware` or `setup-hardware`, or pass --hardware/--serial-port explicitly."
    )


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
        if candidate_supports_required_capabilities(candidate, config=config, registry=registry)
    ]


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
