"""Compatibility facade for the refactored hardware framework."""

from __future__ import annotations

from ._framework_adapters import _profile_dirs_from_config, build_default_registry
from ._framework_doctor import doctor_hardware
from ._framework_locks import hardware_binding_lock, hardware_lock_path
from ._framework_models import (
    DEFAULT_BINDING_FILE,
    DetectedHardware,
    HardwareBinding,
    HardwareBindingStore,
    HardwareDoctorFinding,
    HardwareProfile,
    HardwareRegistry,
    HardwareResolution,
    HardwareResolutionError,
    binding_store_from_config,
    normalize_adapter_request,
)
from ._framework_resolution import (
    candidate_serial_ports,
    detect_hardware,
    resolve_hardware,
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
    "build_registry_from_config",
    "candidate_serial_ports",
    "detect_hardware",
    "doctor_hardware",
    "hardware_binding_lock",
    "hardware_lock_path",
    "normalize_adapter_request",
    "resolve_hardware",
]


def build_registry_from_config(config: dict) -> HardwareRegistry:
    """Build a hardware registry that honors config-defined profile_dirs."""
    return build_default_registry(_profile_dirs_from_config(config))
