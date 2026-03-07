"""Shared helper functions for AUTOGLITCH CLI commands."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from .config import validate_config
from .hardware import binding_store_from_config, normalize_adapter_request
from .plugins import PluginRegistry
from .safety import SafetyController
from .types import ExploitPrimitiveType, GlitchParameters


def _load_run_config(args: argparse.Namespace) -> tuple[dict[str, Any], str | None]:
    if not getattr(args, "template", None):
        return _load_config(Path(args.config), args.target), None

    template_path = Path(args.template)
    if not template_path.exists():
        raise SystemExit(f"template not found: {template_path}")

    with template_path.open("r", encoding="utf-8") as handle:
        template = yaml.safe_load(handle) or {}

    base_config_path = Path(str(template.get("base_config", args.config)))
    target_name = str(template.get("target", args.target))

    config = _load_config(base_config_path, target_name)
    overrides = {
        key: value
        for key, value in template.items()
        if key not in {"name", "base_config", "target", "notes"}
    }
    config = _deep_merge(config, overrides)

    return config, str(template.get("name", template_path.stem))


def _resolve_effective_hardware_mode(
    args: argparse.Namespace,
    config: dict[str, Any] | None = None,
) -> str:
    cli_mode = normalize_adapter_request(getattr(args, "hardware", None))
    if cli_mode == "mock-hardware":
        return "mock"
    if cli_mode in {"serial-command-hardware", "serial-json-hardware"}:
        return "serial"

    resolved_config = config
    if resolved_config is None:
        resolved_config, _ = _load_run_config(args)

    hardware_cfg = resolved_config.get("hardware", {})
    if not isinstance(hardware_cfg, dict):
        return "mock"

    local_binding = None
    try:
        local_binding = binding_store_from_config(
            resolved_config,
            getattr(args, "binding_file", None),
        ).load()
    except Exception:
        local_binding = None

    if local_binding is not None:
        if local_binding.transport == "serial":
            return "serial"
        if local_binding.transport == "virtual":
            return "mock"
        return str(local_binding.transport).lower()

    adapter_raw = hardware_cfg.get("adapter")
    if str(adapter_raw or "").lower() in {"", "auto", "none"}:
        adapter_raw = hardware_cfg.get("mode")
    adapter = normalize_adapter_request(adapter_raw)
    if adapter == "mock-hardware":
        return "mock"
    if adapter in {"serial-command-hardware", "serial-json-hardware"}:
        return "serial"

    transport = str(hardware_cfg.get("transport", "")).lower()
    if transport:
        if transport == "virtual":
            return "mock"
        return transport

    return str(hardware_cfg.get("mode", "mock")).lower()


def _load_config(base_config_path: Path, target_name: str) -> dict[str, Any]:
    if not base_config_path.exists():
        raise SystemExit(f"base config not found: {base_config_path}")

    with base_config_path.open("r", encoding="utf-8") as handle:
        base_config = yaml.safe_load(handle) or {}

    target_file = base_config_path.parent / "targets" / f"{target_name}.yaml"
    if not target_file.exists():
        raise SystemExit(f"target config not found: {target_file}")

    with target_file.open("r", encoding="utf-8") as handle:
        target_config = yaml.safe_load(handle) or {}

    return _deep_merge(base_config, target_config)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_run_namespace(options: dict[str, Any], cli_plugin_dirs: Iterable[str]) -> argparse.Namespace:
    option_plugin_dirs = options.get("plugin_dir", [])
    if isinstance(option_plugin_dirs, str):
        option_plugin_dirs = [option_plugin_dirs]

    return argparse.Namespace(
        config=options.get("config", "configs/default.yaml"),
        template=options.get("template"),
        config_mode=options.get("config_mode", "strict"),
        target=options.get("target", "stm32f3"),
        trials=options.get("trials"),
        optimizer=options.get("optimizer"),
        bo_backend=options.get("bo_backend"),
        rl_backend=options.get("rl_backend"),
        ai_mode=options.get("ai_mode"),
        policy_file=options.get("policy_file"),
        objective=options.get("objective"),
        enable_llm=bool(options.get("enable_llm", False)),
        target_primitive=options.get("target_primitive"),
        hardware=options.get("hardware"),
        serial_port=options.get("serial_port"),
        serial_timeout=options.get("serial_timeout"),
        serial_io=options.get("serial_io"),
        binding_file=options.get("binding_file"),
        require_preflight=bool(options.get("require_preflight", False)),
        rerun_count=options.get("rerun_count"),
        fixed_seed=options.get("fixed_seed"),
        success_threshold=options.get("success_threshold"),
        run_tag=options.get("run_tag"),
        plugin_dir=[*list(cli_plugin_dirs), *list(option_plugin_dirs)],
    )


def _prepare_queue_jobs(jobs: list[dict[str, Any]], respect_order: bool) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for idx, job in enumerate(jobs, start=1):
        if not isinstance(job, dict):
            raise SystemExit(f"job #{idx} must be mapping")

        enabled = job.get("enabled", True)
        if isinstance(enabled, bool) and not enabled:
            continue

        raw_priority = job.get("priority", 0)
        if isinstance(raw_priority, bool):
            raise SystemExit(f"job #{idx} priority must be int, got bool")

        try:
            priority = int(raw_priority)
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"job #{idx} priority must be int-compatible: {raw_priority}") from exc

        prepared.append({"index": idx, "priority": priority, "job": job})

    if respect_order:
        return prepared

    return sorted(prepared, key=lambda item: (-int(item["priority"]), int(item["index"])))


def _queue_has_serial_jobs(
    prepared_jobs: list[dict[str, Any]],
    defaults: dict[str, Any],
    *,
    cli_plugin_dirs: Iterable[str],
    cli_overrides: dict[str, Any] | None = None,
) -> bool:
    for item in prepared_jobs:
        job = item["job"]
        merged = _deep_merge(defaults, job)
        for key, value in (cli_overrides or {}).items():
            if value is not None:
                merged[key] = value
        run_args = _build_run_namespace(merged, cli_plugin_dirs=cli_plugin_dirs)
        if _resolve_effective_hardware_mode(run_args) == "serial":
            return True
    return False


def _execute_queue_job(
    *,
    item: dict[str, Any],
    defaults: dict[str, Any],
    cli_plugin_dirs: Iterable[str],
    execute_campaign: Callable[[argparse.Namespace], dict[str, Any]],
    cli_overrides: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    idx = int(item["index"])
    priority = int(item["priority"])
    job = item["job"]
    job_name = str(job.get("name", f"job_{idx}"))
    job_key = _queue_job_key(idx, job_name)

    merged = _deep_merge(defaults, job)
    for key, value in (cli_overrides or {}).items():
        if value is not None:
            merged[key] = value
    run_args = _build_run_namespace(merged, cli_plugin_dirs)

    record: dict[str, Any] = {
        "job_index": idx,
        "job_name": job_name,
        "priority": priority,
    }
    try:
        output = execute_campaign(run_args)
        record["status"] = "completed"
        record["result"] = output
    except SystemExit as exc:
        record["status"] = "failed"
        record["error"] = {
            "type": "SystemExit",
            "message": str(exc),
            "code": exc.code,
        }
    except Exception as exc:  # pragma: no cover - defensive runtime path
        record["status"] = "failed"
        record["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    return job_key, record


def _queue_job_key(job_index: int, job_name: str) -> str:
    return f"{job_index}:{job_name}"


def _resolve_queue_checkpoint_path(checkpoint_file: str | None, queue_path: Path) -> Path:
    if checkpoint_file:
        return Path(checkpoint_file)
    return Path("experiments/results") / f"queue_checkpoint_{queue_path.stem}.json"


def _create_queue_checkpoint_template(queue_path: Path, queue_digest: str) -> dict[str, Any]:
    now = datetime.now().isoformat()
    return {
        "schema_version": 1,
        "queue": str(queue_path.resolve()),
        "queue_digest": queue_digest,
        "created_at": now,
        "updated_at": now,
        "completed_job_keys": [],
        "jobs": {},
    }


def _load_queue_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _update_queue_checkpoint(
    *,
    checkpoint_data: dict[str, Any],
    checkpoint_file: Path,
    completed_keys: set[str],
    job_key: str,
    job_name: str,
    job_index: int,
    priority: int,
    status: str,
    error: dict[str, Any] | None,
) -> None:
    checkpoint_data.setdefault("jobs", {})
    checkpoint_data["jobs"][job_key] = {
        "job_name": job_name,
        "job_index": job_index,
        "priority": priority,
        "status": status,
        "updated_at": datetime.now().isoformat(),
        "error": error,
    }
    checkpoint_data["completed_job_keys"] = sorted(completed_keys)
    checkpoint_data["updated_at"] = datetime.now().isoformat()

    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_file.write_text(json.dumps(checkpoint_data, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_serial_soak(args: argparse.Namespace) -> bool:
    return _resolve_effective_hardware_mode(args) == "serial"


def _execute_soak_batch(
    *,
    args: argparse.Namespace,
    batch_index: int,
    base_seed: int,
    start_monotonic: float,
    execute_campaign: Callable[[argparse.Namespace], dict[str, Any]],
) -> dict[str, Any]:
    run_args = argparse.Namespace(
        config=args.config,
        template=args.template,
        config_mode=getattr(args, "config_mode", "strict"),
        target=args.target,
        trials=int(args.batch_trials),
        optimizer=args.optimizer,
        bo_backend=args.bo_backend,
        rl_backend=getattr(args, "rl_backend", None),
        ai_mode=getattr(args, "ai_mode", None),
        policy_file=getattr(args, "policy_file", None),
        objective=getattr(args, "objective", None),
        enable_llm=args.enable_llm,
        target_primitive=args.target_primitive,
        hardware=args.hardware,
        serial_port=args.serial_port,
        serial_timeout=args.serial_timeout,
        serial_io=getattr(args, "serial_io", None),
        require_preflight=False,
        rerun_count=1,
        fixed_seed=int(base_seed + batch_index),
        success_threshold=args.success_threshold,
        run_tag=getattr(args, "run_tag", None),
        plugin_dir=list(args.plugin_dir),
    )

    batch_id = batch_index + 1
    try:
        output = execute_campaign(run_args)
        run = dict(output["runs"][0])
        run["batch"] = batch_id
        run["elapsed_s"] = time.monotonic() - start_monotonic
        run["status"] = "completed"
        return run
    except SystemExit as exc:
        return {
            "batch": batch_id,
            "elapsed_s": time.monotonic() - start_monotonic,
            "status": "failed",
            "error": {
                "type": "SystemExit",
                "message": str(exc),
                "code": exc.code,
            },
        }
    except Exception as exc:  # pragma: no cover - defensive runtime path
        return {
            "batch": batch_id,
            "elapsed_s": time.monotonic() - start_monotonic,
            "status": "failed",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }


def _resolve_soak_checkpoint_path(args: argparse.Namespace) -> Path:
    if args.checkpoint_file:
        return Path(args.checkpoint_file)

    name = args.target
    if args.template:
        name = Path(args.template).stem
    return Path("experiments/results") / f"soak_checkpoint_{name}.json"


def _build_soak_resume_key(args: argparse.Namespace) -> str:
    key_payload = {
        "config": args.config,
        "template": args.template,
        "config_mode": getattr(args, "config_mode", "strict"),
        "target": args.target,
        "batch_trials": int(args.batch_trials),
        "optimizer": args.optimizer,
        "bo_backend": args.bo_backend,
        "rl_backend": getattr(args, "rl_backend", None),
        "ai_mode": getattr(args, "ai_mode", None),
        "policy_file": getattr(args, "policy_file", None),
        "objective": getattr(args, "objective", None),
        "enable_llm": bool(args.enable_llm),
        "target_primitive": args.target_primitive,
        "hardware": args.hardware,
        "serial_port": args.serial_port,
        "serial_timeout": args.serial_timeout,
        "serial_io": getattr(args, "serial_io", None),
        "require_preflight": bool(getattr(args, "require_preflight", False)),
        "fixed_seed": args.fixed_seed,
        "success_threshold": args.success_threshold,
        "run_tag": getattr(args, "run_tag", None),
        "plugin_dir": list(args.plugin_dir),
        "max_workers": int(args.max_workers),
        "batch_interval_s": float(args.batch_interval_s),
        "allow_parallel_serial": bool(args.allow_parallel_serial),
    }
    encoded = json.dumps(key_payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _create_soak_checkpoint_template(args: argparse.Namespace, soak_key: str) -> dict[str, Any]:
    now = datetime.now().isoformat()
    return {
        "schema_version": 1,
        "mode": "soak",
        "target": args.target,
        "template": args.template,
        "batch_trials": int(args.batch_trials),
        "run_tag": getattr(args, "run_tag", None),
        "soak_key": soak_key,
        "created_at": now,
        "updated_at": now,
        "next_batch": 1,
        "runs": [],
    }


def _load_soak_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _update_soak_checkpoint(
    checkpoint_data: dict[str, Any],
    checkpoint_file: Path,
    runs: list[dict[str, Any]],
    soak_key: str,
    next_batch: int,
) -> None:
    checkpoint_data["soak_key"] = soak_key
    checkpoint_data["runs"] = runs
    checkpoint_data["next_batch"] = next_batch
    checkpoint_data["updated_at"] = datetime.now().isoformat()

    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_file.write_text(json.dumps(checkpoint_data, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_primitive(value: str | None) -> ExploitPrimitiveType | None:
    if value is None:
        return None

    normalized = value.strip().upper()
    if normalized in ExploitPrimitiveType.__members__:
        return ExploitPrimitiveType[normalized]

    raise SystemExit(
        f"unknown primitive: {value}. use one of {', '.join(ExploitPrimitiveType.__members__.keys())}"
    )


def _aggregate_rerun_results(
    run_summaries: list[dict[str, Any]],
    success_threshold: float,
) -> dict[str, Any]:
    success_rates = [float(run["success_rate"]) for run in run_summaries] if run_summaries else []
    repro_rates = [float(run["primitive_repro_rate"]) for run in run_summaries] if run_summaries else []

    primitive_trials: list[int] = [
        int(value)
        for value in (run.get("time_to_first_primitive") for run in run_summaries)
        if value is not None
    ]

    stable_hits = sum(1 for rate in repro_rates if rate >= success_threshold)

    return {
        "success_rate_mean": mean(success_rates) if success_rates else 0.0,
        "success_rate_min": min(success_rates) if success_rates else 0.0,
        "success_rate_max": max(success_rates) if success_rates else 0.0,
        "primitive_repro_rate_mean": mean(repro_rates) if repro_rates else 0.0,
        "primitive_repro_rate_min": min(repro_rates) if repro_rates else 0.0,
        "primitive_repro_rate_max": max(repro_rates) if repro_rates else 0.0,
        "stable_runs": stable_hits,
        "stable_run_ratio": (stable_hits / len(run_summaries)) if run_summaries else 0.0,
        "time_to_first_primitive_best": min(primitive_trials) if primitive_trials else None,
    }


def _write_json_report(
    prefix: str,
    payload: Mapping[str, Any],
    output_dir: Path = Path("experiments/results"),
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return path


def _latest_report(report_dir: Path) -> Path | None:
    if not report_dir.exists():
        return None

    reports = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def summarize_trial_records(trials: list[dict[str, Any]]) -> dict[str, Any]:
    n_trials = len(trials)
    if n_trials == 0:
        return {
            "n_trials": 0,
            "success_rate": 0.0,
            "primitive_repro_rate": 0.0,
            "time_to_first_primitive": None,
            "fault_distribution": {},
            "primitive_distribution": {},
        }

    success_faults = 0
    fault_dist: dict[str, int] = {}
    primitive_dist: dict[str, int] = {}
    first_primitive_trial: int | None = None

    for idx, trial in enumerate(trials, start=1):
        fault = str(trial.get("fault_class", "UNKNOWN")).upper()
        fault_dist[fault] = fault_dist.get(fault, 0) + 1

        if fault not in {"NORMAL", "RESET", "UNKNOWN"}:
            success_faults += 1

        primitive_value = trial.get("primitive", {})
        primitive_name = "NONE"
        if isinstance(primitive_value, dict):
            primitive_name = str(primitive_value.get("type", "NONE")).upper()
        elif isinstance(primitive_value, str):
            primitive_name = primitive_value.upper()

        if primitive_name != "NONE":
            primitive_dist[primitive_name] = primitive_dist.get(primitive_name, 0) + 1
            trial_id = int(trial.get("trial_id", idx))
            if first_primitive_trial is None:
                first_primitive_trial = trial_id

    primitive_repro_rate = 0.0
    if primitive_dist:
        primitive_repro_rate = max(primitive_dist.values()) / n_trials

    return {
        "n_trials": n_trials,
        "success_rate": success_faults / n_trials,
        "primitive_repro_rate": primitive_repro_rate,
        "time_to_first_primitive": first_primitive_trial,
        "fault_distribution": fault_dist,
        "primitive_distribution": primitive_dist,
    }


def compare_summary_to_report(summary: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    checks = {}
    for key in ("n_trials", "success_rate", "primitive_repro_rate", "time_to_first_primitive"):
        summary_value = summary.get(key)
        report_value = report.get(key)
        if isinstance(summary_value, float) and isinstance(report_value, float):
            match = abs(summary_value - report_value) < 1e-9
        else:
            match = summary_value == report_value
        checks[key] = {
            "summary": summary_value,
            "report": report_value,
            "match": match,
        }

    return {
        "all_match": all(item["match"] for item in checks.values()),
        "checks": checks,
    }


def _build_preflight_safe_params(config: dict[str, Any]) -> GlitchParameters:
    params_cfg = config.get("glitch", {}).get("parameters", {})

    width_cfg = params_cfg.get("width", {})
    offset_cfg = params_cfg.get("offset", {})
    voltage_cfg = params_cfg.get("voltage", {})
    repeat_cfg = params_cfg.get("repeat", {})
    ext_offset_cfg = params_cfg.get("ext_offset", {})

    width = (float(width_cfg.get("min", 0.0)) + float(width_cfg.get("max", 0.0))) / 2.0
    offset = (float(offset_cfg.get("min", 0.0)) + float(offset_cfg.get("max", 0.0))) / 2.0
    voltage_min = float(voltage_cfg.get("min", -1.0))
    voltage_max = float(voltage_cfg.get("max", 1.0))
    voltage = max(voltage_min, min(voltage_max, 0.0))
    repeat = int(max(int(repeat_cfg.get("min", 1)), 1))
    ext_offset = float(ext_offset_cfg.get("min", 0.0))

    return GlitchParameters(
        width=width,
        offset=offset,
        voltage=voltage,
        repeat=repeat,
        ext_offset=ext_offset,
    )


def _resolve_preflight_output_path(path: str | None) -> Path | None:
    if path is None:
        return None
    return Path(path)


def _synthetic_reward(params: GlitchParameters) -> float:
    width_term = max(0.0, 1.0 - abs(float(params.width) - 20.0) / 30.0)
    offset_term = max(0.0, 1.0 - abs(float(params.offset) - 15.0) / 30.0)
    voltage_penalty = min(1.0, abs(float(params.voltage)) / 1.0)
    repeat_penalty = min(1.0, abs(float(params.repeat) - 3.0) / 10.0)
    reward = 0.6 * width_term + 0.4 * offset_term - 0.2 * voltage_penalty - 0.1 * repeat_penalty
    return float(max(0.0, min(1.0, reward)))


def _mean_reward_from_history(optimizer: Any) -> float:
    history = getattr(optimizer, "_history", [])
    if not history:
        return 0.0
    rewards = [float(item[1]) for item in history]
    return float(mean(rewards)) if rewards else 0.0


def _resolve_run_tag(args: argparse.Namespace, config: dict[str, Any]) -> str | None:
    cli_tag = getattr(args, "run_tag", None)
    if cli_tag:
        return str(cli_tag)
    logging_tag = config.get("logging", {}).get("run_tag")
    if logging_tag:
        return str(logging_tag)
    return None


def _resolve_ai_mode(args: argparse.Namespace, config: dict[str, Any]) -> str:
    cli_mode = getattr(args, "ai_mode", None)
    if cli_mode:
        return str(cli_mode)
    cfg_mode = config.get("ai", {}).get("mode")
    if isinstance(cfg_mode, str) and cfg_mode:
        return cfg_mode
    return "off"


def _resolve_policy_file(args: argparse.Namespace, config: dict[str, Any]) -> str | None:
    cli_policy = getattr(args, "policy_file", None)
    if cli_policy:
        return str(cli_policy)
    cfg_policy = config.get("ai", {}).get("policy_file")
    if isinstance(cfg_policy, str) and cfg_policy:
        return cfg_policy
    default_policy = Path("configs/policy/default_policy.yaml")
    if default_policy.exists():
        return str(default_policy)
    return None


def _runtime_fingerprint(*, config_hash_payload: dict[str, Any], store_enabled: bool) -> dict[str, Any]:
    config_json = json.dumps(config_hash_payload, sort_keys=True, ensure_ascii=False)
    payload: dict[str, Any] = {
        "enabled": bool(store_enabled),
        "config_hash_sha256": hashlib.sha256(config_json.encode("utf-8")).hexdigest(),
    }
    if not store_enabled:
        return payload

    payload.update(
        {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
        }
    )

    git_sha = _safe_git_output(["git", "rev-parse", "HEAD"])
    git_dirty = _safe_git_output(["git", "status", "--porcelain"])
    if git_sha:
        payload["git_sha"] = git_sha
    payload["git_dirty"] = bool(git_dirty)
    return payload


def _safe_git_output(cmd: list[str]) -> str | None:
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None
    return output or None


def _load_plugin_registry(config: dict[str, Any], cli_plugin_dirs: Iterable[str]) -> PluginRegistry:
    cfg_plugin_dirs = config.get("plugins", {}).get("manifest_dirs", [])
    all_dirs = [Path(path) for path in [*cfg_plugin_dirs, *cli_plugin_dirs] if path]
    return PluginRegistry.load_default(extra_dirs=all_dirs)


def _snapshot_optimizer_telemetry(optimizer: Any) -> dict[str, Any]:
    snapshot = getattr(optimizer, "telemetry_snapshot", None)
    if callable(snapshot):
        try:
            payload = snapshot()
            if isinstance(payload, dict):
                return payload
        except Exception as exc:  # pragma: no cover - defensive fallback
            return {
                "enabled": False,
                "error": str(exc),
            }

    return {
        "enabled": False,
        "backend_in_use": str(getattr(optimizer, "backend_in_use", type(optimizer).__name__)),
    }


def _validate_runtime_config(config: dict[str, Any], mode: str = "strict") -> list[str]:
    errors = validate_config(config, mode=mode)
    safety = SafetyController.from_config(config)
    errors.extend(safety.validate_config(config))

    recovery_cfg = config.get("recovery", {})
    retry_cfg = recovery_cfg.get("retry", {})
    if int(retry_cfg.get("max_attempts", 3)) <= 0:
        errors.append("recovery.retry.max_attempts must be > 0")

    breaker_cfg = recovery_cfg.get("circuit_breaker", {})
    if int(breaker_cfg.get("failure_threshold", 5)) <= 0:
        errors.append("recovery.circuit_breaker.failure_threshold must be > 0")
    if float(breaker_cfg.get("recovery_timeout_s", 10.0)) < 0:
        errors.append("recovery.circuit_breaker.recovery_timeout_s must be >= 0")

    return errors
