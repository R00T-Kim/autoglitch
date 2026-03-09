"""HIL preflight helpers for the AUTOGLITCH CLI."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import Any

from .cli_support import (
    _build_preflight_safe_params,
    _resolve_effective_hardware_mode,
    _resolve_preflight_output_path,
    _write_json_report,
)
from .runtime import HilPreflightThresholds, run_hil_preflight

LoadRunConfig = Callable[[argparse.Namespace], tuple[dict[str, Any], str | None]]
ValidateRuntimeConfig = Callable[..., list[str]]
CreateHardware = Callable[..., Any]


def hil_preflight_command(
    args: argparse.Namespace,
    *,
    load_run_config: LoadRunConfig,
    validate_runtime_config: ValidateRuntimeConfig,
    run_hil_preflight_for_args: Callable[..., dict[str, Any] | None],
) -> None:
    config, template_name = load_run_config(args)
    errors = validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    result = run_hil_preflight_for_args(args, config=config, force=True)
    if result is None:
        payload = {
            "schema_version": 1,
            "template": template_name,
            "valid": True,
            "skipped": True,
            "reason": "non_serial_hardware",
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    result["template"] = template_name
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if not bool(result.get("valid", False)):
        raise SystemExit(2)


def run_hil_preflight_for_args(
    args: argparse.Namespace,
    *,
    config: dict[str, Any] | None = None,
    force: bool = False,
    load_run_config: LoadRunConfig,
    create_hardware: CreateHardware,
) -> dict[str, Any] | None:
    config_payload = config or load_run_config(args)[0]
    hw_cfg = config_payload.get("hardware", {})
    mode = _resolve_effective_hardware_mode(args, config=config_payload)
    if mode != "serial":
        return None

    serial_cfg = hw_cfg.get("serial", {}) if isinstance(hw_cfg.get("serial", {}), dict) else {}
    preflight_cfg = (
        serial_cfg.get("preflight", {}) if isinstance(serial_cfg.get("preflight", {}), dict) else {}
    )
    enabled = bool(preflight_cfg.get("enabled", True))
    if not enabled and not force:
        return None

    probe_trials = int(
        args.probe_trials
        if getattr(args, "probe_trials", None) is not None
        else preflight_cfg.get("probe_trials", 30)
    )
    thresholds = HilPreflightThresholds(
        max_timeout_rate=float(
            args.max_timeout_rate
            if getattr(args, "max_timeout_rate", None) is not None
            else preflight_cfg.get("max_timeout_rate", 0.05)
        ),
        max_reset_rate=float(
            args.max_reset_rate
            if getattr(args, "max_reset_rate", None) is not None
            else preflight_cfg.get("max_reset_rate", 0.10)
        ),
        max_p95_latency_s=float(
            args.max_p95_latency_s
            if getattr(args, "max_p95_latency_s", None) is not None
            else preflight_cfg.get("max_p95_latency_s", 0.50)
        ),
    )

    safe_params = _build_preflight_safe_params(config_payload)
    hardware = create_hardware(
        args=args,
        config=config_payload,
        seed=int(config_payload.get("experiment", {}).get("seed", 42)),
    )

    try:
        result = run_hil_preflight(
            hardware=hardware,
            safe_params=safe_params,
            probe_trials=probe_trials,
            thresholds=thresholds,
            target_name=str(
                config_payload.get("target", {}).get("name", getattr(args, "target", "unknown"))
            ),
            hardware_mode=mode,
        )
    finally:
        disconnect = getattr(hardware, "disconnect", None)
        if callable(disconnect):
            disconnect()

    output_path = _resolve_preflight_output_path(getattr(args, "output", None))
    if output_path is None:
        output_path = _write_json_report("hil_preflight", result)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    result["report"] = str(output_path)
    return result
