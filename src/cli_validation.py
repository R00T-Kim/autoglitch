"""Release-candidate HIL validation workflow helpers."""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import yaml  # type: ignore[import-untyped]

from .cli_batch import queue_run, soak_run
from .cli_support import _build_run_namespace, _write_json_report
from .hardware import (
    binding_store_from_config,
    detect_hardware,
    doctor_hardware,
    hardware_binding_lock,
    resolve_hardware,
)

LoadRunConfig = Callable[[argparse.Namespace], tuple[dict[str, Any], str | None]]
ValidateRuntimeConfig = Callable[..., list[str]]
ExecuteCampaign = Callable[[argparse.Namespace], dict[str, Any]]
RunHilPreflightForArgs = Callable[..., dict[str, Any] | None]

PRIMARY_REQUIRED_CAPABILITIES = [
    "glitch.execute",
    "target.reset",
    "target.trigger",
    "healthcheck",
]
MANUAL_DRILLS = {
    "bridge_restart": "Restart the control bridge/service and rerun detect/doctor/preflight once.",
    "link_drop": "Disconnect and reconnect the serial link once, then rerun doctor/preflight.",
}


def validate_hil_rc_command(
    args: argparse.Namespace,
    *,
    load_run_config: LoadRunConfig,
    validate_runtime_config: ValidateRuntimeConfig,
    execute_campaign: ExecuteCampaign,
    run_hil_preflight_for_args: RunHilPreflightForArgs,
) -> None:
    config, template_name = load_run_config(args)
    errors = validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    run_tag = getattr(args, "run_tag", None) or f"hil_rc_{args.target}"
    primary_adapter = str(getattr(args, "hardware", None) or "serial-json-hardware")
    output_dir = Path("experiments/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    software_gate = _run_software_gate() if not bool(getattr(args, "skip_software_gate", False)) else {
        "status": "skipped",
        "ok": False,
        "reason": "skip_software_gate",
    }

    primary_config = _prepare_primary_config(args, config, primary_adapter=primary_adapter)
    onboarding = _run_primary_onboarding(
        args=args,
        config=primary_config,
        primary_adapter=primary_adapter,
        force_setup=bool(getattr(args, "force_setup", False)),
    )
    preflight = _run_primary_preflight(
        args=args,
        config=primary_config,
        run_hil_preflight_for_args=run_hil_preflight_for_args,
    )

    warmup = _run_campaign_stage(
        base_args=args,
        execute_campaign=execute_campaign,
        trials=int(getattr(args, "warmup_trials", 100)),
        seeds=[int(getattr(args, "warmup_seed", 42))],
        run_tag=f"{run_tag}_warmup",
    )
    stability = _run_campaign_stage(
        base_args=args,
        execute_campaign=execute_campaign,
        trials=int(getattr(args, "stability_trials", 300)),
        seeds=_parse_seed_csv(str(getattr(args, "stability_seeds", "101,202,303"))),
        run_tag=f"{run_tag}_stability",
    )
    repro = _run_campaign_stage(
        base_args=args,
        execute_campaign=execute_campaign,
        trials=int(getattr(args, "repro_trials", 200)),
        seeds=_parse_seed_csv(str(getattr(args, "repro_seeds", "11,12,13,14,15"))),
        run_tag=f"{run_tag}_repro",
    )

    queue_safety = _run_queue_guard_drill(args=args, output_dir=output_dir)
    binding_lock = _run_binding_lock_drill(onboarding["selected_binding"])
    stale_binding = _run_stale_binding_drill(
        config=primary_config,
        selected_binding=onboarding["selected_binding"],
        output_dir=output_dir,
    )
    soak = _run_soak_resume_drill(
        args=args,
        base_config=config,
        execute_campaign=execute_campaign,
        output_dir=output_dir,
        run_tag=run_tag,
        run_hil_preflight_for_args=run_hil_preflight_for_args,
    )
    legacy_smoke = _run_legacy_smoke(
        args=args,
        config=config,
        selected_binding=onboarding["selected_binding"],
        execute_campaign=execute_campaign,
        run_hil_preflight_for_args=run_hil_preflight_for_args,
    )
    manual_drills = _manual_drill_status(args)

    automated_gates = _evaluate_automated_gates(
        software_gate=software_gate,
        onboarding=onboarding,
        preflight=preflight,
        warmup=warmup,
        stability=stability,
        repro=repro,
        queue_safety=queue_safety,
        binding_lock=binding_lock,
        stale_binding=stale_binding,
        soak=soak,
        legacy_smoke=legacy_smoke,
    )
    manual_confirmed = all(item["confirmed"] for item in manual_drills.values())
    release_candidate_ready = bool(automated_gates["automated_rc_valid"]) and manual_confirmed

    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "run_tag": run_tag,
        "primary_adapter": primary_adapter,
        "gate_level": "release_candidate",
        "software_gate": software_gate,
        "onboarding": onboarding,
        "preflight": preflight,
        "warmup": warmup,
        "stability": stability,
        "repro": repro,
        "queue_safety": queue_safety,
        "binding_lock": binding_lock,
        "stale_binding": stale_binding,
        "soak": soak,
        "legacy_smoke": legacy_smoke,
        "manual_drills": manual_drills,
        "gate_criteria": {
            "required_capabilities": list(PRIMARY_REQUIRED_CAPABILITIES),
            "preflight": {
                "probe_trials": int(getattr(args, "preflight_probe_trials", 50)),
                "max_timeout_rate": float(getattr(args, "preflight_max_timeout_rate", 0.03)),
                "max_reset_rate": float(getattr(args, "preflight_max_reset_rate", 0.08)),
                "max_p95_latency_s": float(getattr(args, "preflight_max_p95_latency_s", 0.40)),
            },
            "primitive_repro_rate_mean_min": 0.20,
            "success_rate_mean_min": 0.30,
            "runtime_failure_ratio_max": 0.10,
            "runtime_failure_ratio_aggregate_max": 0.15,
            "throughput_floor_ratio_vs_warmup": 0.80,
        },
        "gate_results": {
            **automated_gates,
            "manual_drills_confirmed": manual_confirmed,
            "release_candidate_ready": release_candidate_ready,
        },
    }

    output_path = _write_final_report(payload, output=getattr(args, "output", None))
    payload["report"] = str(output_path)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if not release_candidate_ready:
        raise SystemExit(2)


def _run_software_gate() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        check=False,
        capture_output=True,
        text=True,
    )
    text = (completed.stdout or "") + (completed.stderr or "")
    match = re.search(r"(?P<passed>\d+) passed(?:, (?P<skipped>\d+) skipped)?", text)
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "ok": completed.returncode == 0,
        "command": [sys.executable, "-m", "pytest", "-q"],
        "returncode": completed.returncode,
        "passed": int(match.group("passed")) if match else None,
        "skipped": int(match.group("skipped") or 0) if match else None,
        "output_tail": text.strip().splitlines()[-10:],
    }


def _prepare_primary_config(
    args: argparse.Namespace,
    config: dict[str, Any],
    *,
    primary_adapter: str,
) -> dict[str, Any]:
    prepared = copy.deepcopy(config)
    hw_cfg = prepared.setdefault("hardware", {})
    hw_cfg["mode"] = "auto"
    hw_cfg["auto_detect"] = True
    hw_cfg["preferred_adapter"] = primary_adapter
    if getattr(args, "binding_file", None):
        hw_cfg["binding_file"] = str(args.binding_file)
    if getattr(args, "serial_port", None):
        hw_cfg.setdefault("discovery", {})["candidate_ports"] = [str(args.serial_port)]
        hw_cfg.setdefault("target", {})["port"] = None

    existing_caps = hw_cfg.get("required_capabilities", [])
    if isinstance(existing_caps, str):
        existing_caps = [existing_caps]
    caps = {str(item) for item in existing_caps if str(item)}
    caps.update(PRIMARY_REQUIRED_CAPABILITIES)
    hw_cfg["required_capabilities"] = sorted(caps)
    return prepared


def _run_primary_onboarding(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    primary_adapter: str,
    force_setup: bool,
) -> dict[str, Any]:
    binding_store = binding_store_from_config(config, getattr(args, "binding_file", None))
    candidates = detect_hardware(
        config=config,
        explicit_adapter=primary_adapter,
        explicit_port=getattr(args, "serial_port", None),
    )
    resolution = resolve_hardware(
        config=config,
        explicit_adapter=primary_adapter,
        explicit_port=getattr(args, "serial_port", None),
        seed=int(config.get("experiment", {}).get("seed", 42)),
        binding_file=getattr(args, "binding_file", None),
    )

    existing = binding_store.load() if binding_store.path.exists() else None
    existing_matches = existing is not None and _binding_equivalent(existing.to_dict(), resolution.selected.to_dict())
    wrote_binding = False
    if existing is None:
        binding_store.save(resolution.selected, selected_from=resolution.source, candidates=resolution.candidates)
        wrote_binding = True
    elif not existing_matches:
        if not force_setup:
            raise SystemExit(
                f"binding file {binding_store.path} already exists with a different adapter/location; rerun with --force-setup"
            )
        binding_store.save(resolution.selected, selected_from=resolution.source, candidates=resolution.candidates)
        wrote_binding = True

    doctor = doctor_hardware(
        config=config,
        explicit_adapter=None,
        explicit_port=None,
        binding_file=str(binding_store.path),
        seed=int(config.get("experiment", {}).get("seed", 42)),
    )
    ok = (
        resolution.selected.adapter_id == primary_adapter
        and len(candidates) >= 1
        and doctor.get("status") == "ok"
    )
    return {
        "ok": ok,
        "binding_file": str(binding_store.path),
        "candidate_count": len(candidates),
        "candidates": [candidate.to_dict() for candidate in candidates],
        "selected_binding": resolution.selected.to_dict(),
        "selected_from": resolution.source,
        "wrote_binding": wrote_binding,
        "doctor": doctor,
    }


def _run_primary_preflight(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    run_hil_preflight_for_args: RunHilPreflightForArgs,
) -> dict[str, Any]:
    preflight_args = copy.copy(args)
    preflight_args.hardware = None
    preflight_args.serial_port = None
    preflight_args.probe_trials = int(getattr(args, "preflight_probe_trials", 50))
    preflight_args.max_timeout_rate = float(getattr(args, "preflight_max_timeout_rate", 0.03))
    preflight_args.max_reset_rate = float(getattr(args, "preflight_max_reset_rate", 0.08))
    preflight_args.max_p95_latency_s = float(getattr(args, "preflight_max_p95_latency_s", 0.40))
    result = run_hil_preflight_for_args(preflight_args, config=config, force=True)
    if result is None:
        raise SystemExit("validate-hil-rc requires serial-capable resolved hardware")
    return result


def _run_campaign_stage(
    *,
    base_args: argparse.Namespace,
    execute_campaign: ExecuteCampaign,
    trials: int,
    seeds: list[int],
    run_tag: str,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for seed in seeds:
        run_args = _build_run_namespace(
            {
                "config": getattr(base_args, "config", "configs/default.yaml"),
                "template": getattr(base_args, "template", None),
                "config_mode": getattr(base_args, "config_mode", "strict"),
                "target": getattr(base_args, "target", "stm32f3"),
                "trials": int(trials),
                "optimizer": "bayesian",
                "bo_backend": "heuristic",
                "rl_backend": None,
                "ai_mode": "off",
                "policy_file": None,
                "objective": "single",
                "enable_llm": False,
                "target_primitive": None,
                "hardware": None,
                "serial_port": None,
                "serial_timeout": getattr(base_args, "serial_timeout", None),
                "serial_io": getattr(base_args, "serial_io", None),
                "binding_file": getattr(base_args, "binding_file", None),
                "require_preflight": False,
                "rerun_count": 1,
                "fixed_seed": int(seed),
                "success_threshold": 0.30,
                "run_tag": run_tag,
                "plugin_dir": list(getattr(base_args, "plugin_dir", [])),
            },
            cli_plugin_dirs=[],
        )
        output = execute_campaign(run_args)
        run_summary = dict(output["runs"][0])
        report_payload = json.loads(Path(str(run_summary["report"])).read_text(encoding="utf-8"))
        runs.append(
            {
                "seed": int(seed),
                "n_trials": int(run_summary["n_trials"]),
                "run_id": run_summary["run_id"],
                "report": run_summary["report"],
                "manifest": run_summary["manifest"],
                "log": run_summary["log"],
                "success_rate": float(run_summary["success_rate"]),
                "primitive_repro_rate": float(run_summary["primitive_repro_rate"]),
                "runtime_total_seconds": float(run_summary["runtime_total_seconds"]),
                "throughput_trials_per_second": float(
                    report_payload.get("runtime", {}).get("throughput_trials_per_second", 0.0)
                ),
                "latency_p95_seconds": float(report_payload.get("latency", {}).get("p95_seconds", 0.0)),
                "runtime_failure_ratio": _runtime_failure_ratio(run_summary),
                "error_breakdown": dict(run_summary.get("error_breakdown", {})),
            }
        )
    return {
        "trials": int(trials),
        "seeds": [int(seed) for seed in seeds],
        "runs": runs,
        "aggregate": _aggregate_validation_runs(runs),
    }


def _run_queue_guard_drill(*, args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    queue_path = output_dir / f"queue_guard_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.yaml"
    payload = {
        "schema_version": 1,
        "defaults": {
            "config": getattr(args, "config", "configs/default.yaml"),
            "target": getattr(args, "target", "stm32f3"),
            "binding_file": getattr(args, "binding_file", None),
            "trials": 1,
        },
        "jobs": [{"name": "serial_guard"}],
    }
    queue_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    queue_args = argparse.Namespace(
        queue=str(queue_path),
        plugin_dir=list(getattr(args, "plugin_dir", [])),
        config_mode=getattr(args, "config_mode", "strict"),
        serial_io=getattr(args, "serial_io", None),
        rl_backend=None,
        ai_mode="off",
        policy_file=None,
        require_preflight=False,
        run_tag=f"{getattr(args, 'run_tag', 'hil_rc')}_queue_guard",
        checkpoint_file=str(output_dir / "queue_guard_checkpoint.json"),
        resume=False,
        continue_on_error=True,
        respect_order=False,
        max_workers=2,
        job_interval_s=0.0,
        allow_parallel_serial=False,
    )
    try:
        queue_run(
            queue_args,
            execute_campaign=lambda run_args: (_ for _ in ()).throw(
                AssertionError(f"unexpected campaign execution: {run_args}")
            ),
            write_json_report=_write_json_report,
        )
    except SystemExit as exc:
        message = str(exc)
        return {
            "ok": "parallel serial queue is blocked" in message,
            "message": message,
            "queue": str(queue_path),
        }
    raise SystemExit("queue guard drill did not block parallel serial execution")


def _run_binding_lock_drill(selected_binding: dict[str, Any]) -> dict[str, Any]:
    try:
        with hardware_binding_lock(selected_binding, timeout_s=0.0):
            try:
                with hardware_binding_lock(selected_binding, timeout_s=0.0):
                    raise AssertionError("binding lock should not be re-acquired")
            except RuntimeError as exc:
                return {"ok": "already in use" in str(exc), "message": str(exc)}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": False, "message": "binding lock drill did not fail as expected"}


def _run_stale_binding_drill(
    *,
    config: dict[str, Any],
    selected_binding: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    stale_binding = copy.deepcopy(selected_binding)
    stale_binding["location"] = "/dev/ttyAUTOGLITCH_STALE"
    stale_path = output_dir / f"stale_binding_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.yaml"
    payload = {"schema_version": 1, "binding": stale_binding}
    stale_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    report = doctor_hardware(
        config=config,
        binding_file=str(stale_path),
        explicit_adapter=None,
        explicit_port=None,
        seed=int(config.get("experiment", {}).get("seed", 42)),
    )
    finding_codes = {item["code"] for item in report.get("findings", [])}
    return {
        "ok": report.get("status") == "degraded"
        and bool({"healthcheck_failed", "binding_not_detected"} & finding_codes),
        "report": report,
        "binding_file": str(stale_path),
    }


def _run_soak_resume_drill(
    *,
    args: argparse.Namespace,
    base_config: dict[str, Any],
    execute_campaign: ExecuteCampaign,
    output_dir: Path,
    run_tag: str,
    run_hil_preflight_for_args: RunHilPreflightForArgs,
) -> dict[str, Any]:
    if bool(getattr(args, "skip_soak", False)):
        return {"ok": False, "status": "skipped", "reason": "skip_soak"}

    checkpoint_path = output_dir / f"soak_rc_checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    soak_base = _build_run_namespace(
        {
            "config": getattr(args, "config", "configs/default.yaml"),
            "template": getattr(args, "template", None),
            "config_mode": getattr(args, "config_mode", "strict"),
            "target": getattr(args, "target", "stm32f3"),
            "optimizer": "bayesian",
            "bo_backend": "heuristic",
            "ai_mode": "off",
            "hardware": None,
            "serial_port": None,
            "serial_timeout": getattr(args, "serial_timeout", None),
            "serial_io": getattr(args, "serial_io", None),
            "binding_file": getattr(args, "binding_file", None),
            "require_preflight": True,
            "fixed_seed": 9001,
            "success_threshold": 0.30,
            "run_tag": f"{run_tag}_soak",
            "plugin_dir": list(getattr(args, "plugin_dir", [])),
            "trials": None,
            "rl_backend": None,
            "policy_file": None,
            "objective": "single",
            "enable_llm": False,
            "target_primitive": None,
        },
        cli_plugin_dirs=[],
    )
    soak_base.batch_trials = int(getattr(args, "soak_batch_trials", 200))
    soak_base.checkpoint_file = str(checkpoint_path)
    soak_base.continue_on_error = True
    soak_base.max_workers = 1
    soak_base.batch_interval_s = 0.0
    soak_base.allow_parallel_serial = False

    first_args = copy.copy(soak_base)
    first_args.duration_minutes = float(getattr(args, "soak_duration_minutes", 120.0))
    first_args.max_batches = 1
    first_args.resume = False

    first_payload, first_elapsed = _capture_json_command(
        soak_run,
        first_args,
        execute_campaign=execute_campaign,
        load_run_config=lambda _args: (copy.deepcopy(base_config), None),
        validate_runtime_config=lambda cfg, mode=None: [],
        run_hil_preflight_for_args=lambda pre_args, **kwargs: run_hil_preflight_for_args(
            pre_args,
            config=copy.deepcopy(base_config),
            force=True,
        ),
        write_json_report=_write_json_report,
    )

    resume_args = copy.copy(soak_base)
    resume_args.duration_minutes = max(
        0.01,
        float(getattr(args, "soak_duration_minutes", 120.0)) - (first_elapsed / 60.0),
    )
    resume_args.max_batches = int(getattr(args, "soak_max_batches", 20))
    resume_args.resume = True

    resume_payload, _ = _capture_json_command(
        soak_run,
        resume_args,
        execute_campaign=execute_campaign,
        load_run_config=lambda _args: (copy.deepcopy(base_config), None),
        validate_runtime_config=lambda cfg, mode=None: [],
        run_hil_preflight_for_args=lambda pre_args, **kwargs: run_hil_preflight_for_args(
            pre_args,
            config=copy.deepcopy(base_config),
            force=True,
        ),
        write_json_report=_write_json_report,
    )
    return {
        "ok": int(resume_payload.get("completed_batches", 0)) >= int(getattr(args, "soak_max_batches", 20)),
        "checkpoint_file": str(checkpoint_path),
        "first": first_payload,
        "resume": resume_payload,
    }


def _run_legacy_smoke(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    selected_binding: dict[str, Any],
    execute_campaign: ExecuteCampaign,
    run_hil_preflight_for_args: RunHilPreflightForArgs,
) -> dict[str, Any]:
    if bool(getattr(args, "skip_legacy_smoke", False)):
        return {"ok": False, "status": "skipped", "reason": "skip_legacy_smoke"}

    legacy_config = copy.deepcopy(config)
    legacy_config.setdefault("hardware", {})["preferred_adapter"] = "serial-command-hardware"
    legacy_args = _build_run_namespace(
        {
            "config": getattr(args, "config", "configs/default.yaml"),
            "template": getattr(args, "template", None),
            "config_mode": getattr(args, "config_mode", "strict"),
            "target": getattr(args, "target", "stm32f3"),
            "trials": int(getattr(args, "legacy_smoke_trials", 50)),
            "optimizer": "bayesian",
            "bo_backend": "heuristic",
            "rl_backend": None,
            "ai_mode": "off",
            "policy_file": None,
            "objective": "single",
            "enable_llm": False,
            "target_primitive": None,
            "hardware": "serial",
            "serial_port": str(selected_binding.get("location", "")),
            "serial_timeout": getattr(args, "serial_timeout", None),
            "serial_io": getattr(args, "serial_io", None),
            "binding_file": getattr(args, "binding_file", None),
            "require_preflight": False,
            "rerun_count": 1,
            "fixed_seed": 5150,
            "success_threshold": 0.30,
            "run_tag": f"{getattr(args, 'run_tag', 'hil_rc')}_legacy",
            "plugin_dir": list(getattr(args, "plugin_dir", [])),
        },
        cli_plugin_dirs=[],
    )
    legacy_args.probe_trials = 10
    legacy_args.max_timeout_rate = 0.50
    legacy_args.max_reset_rate = 0.50
    legacy_args.max_p95_latency_s = 1.0
    legacy_args.output = None

    preflight = run_hil_preflight_for_args(legacy_args, config=legacy_config, force=True)
    if preflight is None:
        return {"ok": False, "status": "failed", "reason": "legacy_preflight_skipped"}

    output = execute_campaign(legacy_args)
    run_summary = dict(output["runs"][0])
    return {
        "ok": bool(preflight.get("valid", False)) and Path(str(run_summary["report"])).exists(),
        "preflight": preflight,
        "run": {
            "report": run_summary["report"],
            "manifest": run_summary["manifest"],
            "log": run_summary["log"],
            "error_breakdown": run_summary.get("error_breakdown", {}),
        },
    }


def _manual_drill_status(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    return {
        key: {
            "description": description,
            "confirmed": bool(getattr(args, f"manual_{key}_ok", False)),
        }
        for key, description in MANUAL_DRILLS.items()
    }


def _evaluate_automated_gates(
    *,
    software_gate: dict[str, Any],
    onboarding: dict[str, Any],
    preflight: dict[str, Any],
    warmup: dict[str, Any],
    stability: dict[str, Any],
    repro: dict[str, Any],
    queue_safety: dict[str, Any],
    binding_lock: dict[str, Any],
    stale_binding: dict[str, Any],
    soak: dict[str, Any],
    legacy_smoke: dict[str, Any],
) -> dict[str, Any]:
    graded_runs = [*stability["runs"], *repro["runs"]]
    graded_aggregate = _aggregate_validation_runs(graded_runs)
    warmup_throughput = float(warmup["aggregate"].get("throughput_mean", 0.0))
    graded_throughput = float(graded_aggregate.get("throughput_mean", 0.0))
    throughput_floor_ok = warmup_throughput <= 0 or graded_throughput >= (warmup_throughput * 0.80)
    per_run_runtime_failure_ok = all(float(run.get("runtime_failure_ratio", 0.0)) <= 0.10 for run in graded_runs)
    aggregate_runtime_failure_ok = float(graded_aggregate.get("runtime_failure_ratio", 0.0)) <= 0.15

    automated_ok = all(
        [
            bool(software_gate.get("ok", False)),
            bool(onboarding.get("ok", False)),
            bool(preflight.get("valid", False)),
            float(graded_aggregate.get("primitive_repro_rate_mean", 0.0)) >= 0.20,
            float(graded_aggregate.get("success_rate_mean", 0.0)) >= 0.30,
            float(graded_aggregate.get("latency_p95_max", 0.0)) <= 0.50,
            throughput_floor_ok,
            per_run_runtime_failure_ok,
            aggregate_runtime_failure_ok,
            bool(queue_safety.get("ok", False)),
            bool(binding_lock.get("ok", False)),
            bool(stale_binding.get("ok", False)),
            bool(soak.get("ok", False)),
            bool(legacy_smoke.get("ok", False)),
        ]
    )
    return {
        "software_gate_ok": bool(software_gate.get("ok", False)),
        "onboarding_ok": bool(onboarding.get("ok", False)),
        "preflight_ok": bool(preflight.get("valid", False)),
        "queue_safety_ok": bool(queue_safety.get("ok", False)),
        "binding_lock_ok": bool(binding_lock.get("ok", False)),
        "stale_binding_ok": bool(stale_binding.get("ok", False)),
        "soak_ok": bool(soak.get("ok", False)),
        "legacy_smoke_ok": bool(legacy_smoke.get("ok", False)),
        "primitive_repro_rate_mean": float(graded_aggregate.get("primitive_repro_rate_mean", 0.0)),
        "success_rate_mean": float(graded_aggregate.get("success_rate_mean", 0.0)),
        "latency_p95_max": float(graded_aggregate.get("latency_p95_max", 0.0)),
        "throughput_floor_ok": throughput_floor_ok,
        "per_run_runtime_failure_ok": per_run_runtime_failure_ok,
        "aggregate_runtime_failure_ok": aggregate_runtime_failure_ok,
        "automated_rc_valid": automated_ok,
    }


def _aggregate_validation_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {
            "count": 0,
            "success_rate_mean": 0.0,
            "primitive_repro_rate_mean": 0.0,
            "latency_p95_max": 0.0,
            "throughput_mean": 0.0,
            "runtime_failure_ratio": 0.0,
        }
    total_trials = sum(max(1, int(run.get("n_trials", 0) or 0)) for run in runs)
    runtime_failures = sum(int(run.get("error_breakdown", {}).get("runtime_failure", 0)) for run in runs)
    return {
        "count": len(runs),
        "success_rate_mean": float(mean(float(run.get("success_rate", 0.0)) for run in runs)),
        "primitive_repro_rate_mean": float(mean(float(run.get("primitive_repro_rate", 0.0)) for run in runs)),
        "latency_p95_max": float(max(float(run.get("latency_p95_seconds", 0.0)) for run in runs)),
        "throughput_mean": float(mean(float(run.get("throughput_trials_per_second", 0.0)) for run in runs)),
        "runtime_failure_ratio": float(runtime_failures / total_trials) if total_trials > 0 else 0.0,
    }


def _binding_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        str(left.get("adapter_id", "")) == str(right.get("adapter_id", ""))
        and str(left.get("transport", "")) == str(right.get("transport", ""))
        and str(left.get("location", "")) == str(right.get("location", ""))
    )


def _runtime_failure_ratio(run_summary: dict[str, Any]) -> float:
    n_trials = max(1, int(run_summary.get("n_trials", 0) or 0))
    failures = int(run_summary.get("error_breakdown", {}).get("runtime_failure", 0))
    return failures / n_trials


def _parse_seed_csv(value: str) -> list[int]:
    seeds = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not seeds:
        raise SystemExit("seed list must not be empty")
    return seeds


def _capture_json_command(
    fn: Callable[..., None],
    args: argparse.Namespace,
    **kwargs: Any,
) -> tuple[dict[str, Any], float]:
    buffer = io.StringIO()
    started = time.monotonic()
    with contextlib.redirect_stdout(buffer):
        fn(args, **kwargs)
    elapsed = time.monotonic() - started
    output = buffer.getvalue().strip()
    if not output:
        raise SystemExit(f"{fn.__name__} produced no JSON output")
    return json.loads(output), elapsed


def _write_final_report(payload: dict[str, Any], *, output: str | None) -> Path:
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
    return _write_json_report("hil_rc_validation", payload)
