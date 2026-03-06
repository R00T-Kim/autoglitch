"""Hardware abstractions, discovery, and implementations."""

from .base import BaseGlitcher, BaseHardwareAdapter, BaseScope, BaseTarget
from .framework import (
    DEFAULT_BINDING_FILE,
    DetectedHardware,
    HardwareBinding,
    HardwareBindingStore,
    HardwareProfile,
    HardwareRegistry,
    HardwareResolution,
    HardwareResolutionError,
    binding_store_from_config,
    build_default_registry,
    detect_hardware,
    doctor_hardware,
    hardware_binding_lock,
    hardware_lock_path,
    normalize_adapter_request,
    resolve_hardware,
)
from .mock import MockHardware
from .serial_async_hardware import AsyncSerialCommandHardware
from .serial_hardware import SerialCommandHardware
from .typed_serial_hardware import TypedSerialCommandHardware

__all__ = [
    "AsyncSerialCommandHardware",
    "BaseGlitcher",
    "BaseHardwareAdapter",
    "BaseScope",
    "BaseTarget",
    "DEFAULT_BINDING_FILE",
    "DetectedHardware",
    "HardwareBinding",
    "HardwareBindingStore",
    "HardwareProfile",
    "HardwareRegistry",
    "HardwareResolution",
    "HardwareResolutionError",
    "MockHardware",
    "SerialCommandHardware",
    "TypedSerialCommandHardware",
    "binding_store_from_config",
    "build_default_registry",
    "detect_hardware",
    "doctor_hardware",
    "hardware_binding_lock",
    "hardware_lock_path",
    "normalize_adapter_request",
    "resolve_hardware",
]
