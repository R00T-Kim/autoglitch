"""Hardware discovery/setup/doctor CLI commands."""
from __future__ import annotations

import argparse
import copy
import json
from collections.abc import Callable
from typing import Any

from .hardware import (
    binding_store_from_config,
    detect_hardware,
    doctor_hardware,
    resolve_hardware,
)

LoadRunConfig = Callable[[argparse.Namespace], tuple[dict[str, Any], str | None]]
ValidateRuntimeConfig = Callable[..., list[str]]


def _prepare_management_config(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    prepared = copy.deepcopy(config)
    hw_cfg = prepared.setdefault("hardware", {})
    requested = str(getattr(args, "hardware", "") or "").strip().lower()
    if requested not in {"mock", "mock-hardware"}:
        hw_cfg["mode"] = "auto"
    if getattr(args, "serial_port", None):
        hw_cfg.setdefault("discovery", {})["candidate_ports"] = [str(args.serial_port)]
        hw_cfg.setdefault("target", {})["port"] = None
    return prepared


def detect_hardware_command(
    args: argparse.Namespace,
    *,
    load_run_config: LoadRunConfig,
    validate_runtime_config: ValidateRuntimeConfig,
) -> None:
    config, template_name = load_run_config(args)
    errors = validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    management_config = _prepare_management_config(args, config)
    candidates = detect_hardware(
        config=management_config,
        explicit_adapter=getattr(args, "hardware", None),
        explicit_port=getattr(args, "serial_port", None),
    )
    payload = {
        "schema_version": 1,
        "template": template_name,
        "binding_file": str(binding_store_from_config(management_config, getattr(args, "binding_file", None)).path),
        "detected": len(candidates),
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))



def setup_hardware_command(
    args: argparse.Namespace,
    *,
    load_run_config: LoadRunConfig,
    validate_runtime_config: ValidateRuntimeConfig,
) -> None:
    config, template_name = load_run_config(args)
    errors = validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    management_config = _prepare_management_config(args, config)
    store = binding_store_from_config(management_config, getattr(args, "binding_file", None))
    if store.path.exists() and not bool(getattr(args, "force", False)):
        raise SystemExit(f"hardware binding already exists: {store.path} (use --force to overwrite)")

    resolution = resolve_hardware(
        config=management_config,
        explicit_adapter=getattr(args, "hardware", None),
        explicit_port=getattr(args, "serial_port", None),
        seed=int(config.get("experiment", {}).get("seed", 42)),
        binding_file=getattr(args, "binding_file", None),
    )
    store.save(resolution.selected, selected_from=resolution.source, candidates=resolution.candidates)

    payload = {
        "schema_version": 1,
        "template": template_name,
        "binding_file": str(store.path),
        "selected_from": resolution.source,
        "binding": resolution.selected.to_dict(),
        "candidate_count": len(resolution.candidates),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))



def doctor_hardware_command(
    args: argparse.Namespace,
    *,
    load_run_config: LoadRunConfig,
    validate_runtime_config: ValidateRuntimeConfig,
) -> None:
    config, template_name = load_run_config(args)
    errors = validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    management_config = _prepare_management_config(args, config)
    report = doctor_hardware(
        config=management_config,
        explicit_adapter=getattr(args, "hardware", None),
        explicit_port=getattr(args, "serial_port", None),
        binding_file=getattr(args, "binding_file", None),
        seed=int(config.get("experiment", {}).get("seed", 42)),
    )
    report["template"] = template_name
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("status") != "ok":
        raise SystemExit(2)
