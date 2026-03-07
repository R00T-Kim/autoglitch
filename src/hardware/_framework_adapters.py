"""Adapter factories, probes, and registry construction for hardware backends."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ._framework_models import (
    DetectedHardware,
    HardwareAdapterDefinition,
    HardwareBinding,
    HardwareProfile,
    HardwareRegistry,
    load_profiles,
    normalize_adapter_request,
)
from .mock import MockHardware
from .serial_async_hardware import AsyncSerialCommandHardware
from .serial_hardware import SerialCommandHardware
from .typed_serial_hardware import TypedSerialCommandHardware


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
