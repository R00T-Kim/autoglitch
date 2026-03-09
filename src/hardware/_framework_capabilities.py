"""Capability filtering helpers for hardware resolution."""

from __future__ import annotations

from typing import Any

from ._framework_models import (
    DetectedHardware,
    HardwareBinding,
    HardwareRegistry,
    HardwareResolutionError,
)


def required_capabilities(config: dict[str, Any]) -> set[str]:
    raw_hw_cfg = config.get("hardware", {})
    hw_cfg = raw_hw_cfg if isinstance(raw_hw_cfg, dict) else {}
    values = hw_cfg.get("required_capabilities", [])
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return set()
    return {str(item).strip() for item in values if str(item).strip()}


def candidate_capabilities(
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


def binding_capabilities(
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


def candidate_supports_required_capabilities(
    candidate: DetectedHardware,
    *,
    config: dict[str, Any],
    registry: HardwareRegistry,
) -> bool:
    required = required_capabilities(config)
    if not required:
        return True
    return required.issubset(candidate_capabilities(candidate, registry=registry))


def validate_required_capabilities(
    *,
    binding: HardwareBinding,
    config: dict[str, Any],
    registry: HardwareRegistry,
) -> None:
    required = required_capabilities(config)
    if not required:
        return
    available = binding_capabilities(binding, registry=registry)
    missing = sorted(required - available)
    if missing:
        raise HardwareResolutionError(
            f"resolved hardware {binding.adapter_id} is missing required capabilities: {', '.join(missing)}"
        )
