"""Diagnostics helpers for hardware resolution."""
from __future__ import annotations

from contextlib import suppress
from typing import Any

from ._framework_adapters import _profile_dirs_from_config, build_default_registry
from ._framework_models import HardwareDoctorFinding, binding_store_from_config
from ._framework_resolution import detect_hardware, resolve_hardware


def doctor_hardware(
    *,
    config: dict[str, Any],
    explicit_adapter: str | None = None,
    explicit_port: str | None = None,
    binding_file: str | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    findings: list[HardwareDoctorFinding] = []
    registry = build_default_registry(_profile_dirs_from_config(config))
    candidates = detect_hardware(
        config=config,
        explicit_adapter=explicit_adapter,
        explicit_port=explicit_port,
        registry=registry,
    )
    store = binding_store_from_config(config, binding_file)
    binding = None
    healthcheck: dict[str, Any] | None = None
    selected_from = "none"
    try:
        resolution = resolve_hardware(
            config=config,
            explicit_adapter=explicit_adapter,
            explicit_port=explicit_port,
            seed=seed,
            registry=registry,
            binding_file=binding_file,
        )
        binding = resolution.selected
        selected_from = resolution.source
        if resolution.source == "local-binding" and candidates and not any(
            candidate.binding.adapter_id == binding.adapter_id
            and candidate.binding.location == binding.location
            for candidate in candidates
        ):
            findings.append(
                HardwareDoctorFinding(
                    "warning",
                    "binding_not_detected",
                    "Saved local binding did not appear in current auto-detect candidates.",
                )
            )

        adapter = registry.create(binding, config, seed)
        try:
            probe = getattr(adapter, "healthcheck", None)
            if callable(probe):
                healthcheck = dict(probe())
                if not bool(healthcheck.get("ok", False)):
                    findings.append(
                        HardwareDoctorFinding(
                            "error",
                            "healthcheck_failed",
                            f"Resolved hardware healthcheck failed for {binding.adapter_id}.",
                        )
                    )
        except Exception as exc:
            findings.append(HardwareDoctorFinding("error", "healthcheck_failed", str(exc)))
        finally:
            disconnect = getattr(adapter, "disconnect", None)
            if callable(disconnect):
                with suppress(Exception):
                    disconnect()
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
        "healthcheck": healthcheck,
        "candidates": [candidate.to_dict() for candidate in candidates],
        "findings": [item.to_dict() for item in findings],
    }
