"""AUTOGLITCH command line interface."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import platform
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

import yaml

from .classifier import RuleBasedClassifier
from .config import validate_config
from .hardware import MockHardware, SerialCommandHardware
from .llm_advisor import LLMAdvisor
from .logging_viz import ExperimentLogger, MLflowTracker
from .mapper import PrimitiveMapper
from .observer import BasicObserver
from .optimizer import BayesianOptimizer, RLOptimizer, SB3Optimizer
from .orchestrator import ExperimentOrchestrator
from .plugins import PluginRegistry
from .runtime import HilPreflightThresholds, RecoveryExecutor, run_hil_preflight
from .safety import SafetyController
from .types import ExploitPrimitiveType, GlitchParameters

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    if args.command == "run":
        _run_campaign(args)
        return

    if args.command == "queue-run":
        _queue_run(args)
        return

    if args.command == "soak":
        _soak_run(args)
        return

    if args.command == "report":
        _show_report(args)
        return

    if args.command == "validate-config":
        _validate_config_cmd(args)
        return

    if args.command == "list-plugins":
        _list_plugins(args)
        return

    if args.command == "benchmark":
        _run_benchmark(args)
        return

    if args.command == "replay":
        _replay_run(args)
        return

    if args.command == "hil-preflight":
        _hil_preflight_cmd(args)
        return

    if args.command == "train-rl":
        _train_rl_cmd(args)
        return

    if args.command == "eval-rl":
        _eval_rl_cmd(args)
        return

    parser.print_help()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AUTOGLITCH CLI")
    parser.add_argument("--log-level", default="INFO", help="logging level (default: INFO)")

    sub = parser.add_subparsers(dest="command")

    # run
    run = sub.add_parser("run", help="run glitch campaign")
    _add_run_arguments(run)

    # queue-run
    queue = sub.add_parser("queue-run", help="run jobs from queue yaml")
    queue.add_argument("--queue", required=True, help="queue YAML path")
    queue.add_argument("--plugin-dir", action="append", default=[], help="extra plugin manifest directory")
    queue.add_argument("--config-mode", choices=["strict", "legacy"], default=None)
    queue.add_argument("--serial-io", choices=["sync", "async"], default=None)
    queue.add_argument("--rl-backend", choices=["lite", "sb3"], default=None)
    queue.add_argument("--run-tag", default=None, help="optional run tag applied to queue jobs")
    queue.add_argument(
        "--require-preflight",
        action="store_true",
        help="require serial HIL preflight pass before each queue job",
    )
    queue.add_argument(
        "--checkpoint-file",
        default=None,
        help="optional checkpoint JSON path (default: experiments/results/queue_checkpoint_<name>.json)",
    )
    queue.add_argument("--resume", action="store_true", help="resume from checkpoint file")
    queue.add_argument(
        "--continue-on-error",
        action="store_true",
        help="continue executing remaining jobs when a job fails",
    )
    queue.add_argument(
        "--respect-order",
        action="store_true",
        help="execute jobs in YAML order (ignore priority field)",
    )
    queue.add_argument("--max-workers", type=int, default=1, help="parallel queue workers (default: 1)")
    queue.add_argument("--job-interval-s", type=float, default=0.0, help="delay between job dispatches")
    queue.add_argument(
        "--allow-parallel-serial",
        action="store_true",
        help="allow max-workers > 1 when job hardware is serial (unsafe by default)",
    )

    # soak
    soak = sub.add_parser("soak", help="long-running soak campaign")
    _add_run_arguments(soak)
    soak.add_argument("--duration-minutes", type=float, default=60.0, help="soak duration in minutes")
    soak.add_argument("--batch-trials", type=int, default=200, help="trials per soak batch")
    soak.add_argument("--max-batches", type=int, default=None, help="optional hard cap for batches")
    soak.add_argument(
        "--checkpoint-file",
        default=None,
        help="optional checkpoint JSON path (default: experiments/results/soak_checkpoint_<name>.json)",
    )
    soak.add_argument("--resume", action="store_true", help="resume from soak checkpoint")
    soak.add_argument(
        "--continue-on-error",
        action="store_true",
        help="continue remaining soak batches even if one batch fails",
    )
    soak.add_argument("--max-workers", type=int, default=1, help="parallel soak batch workers (default: 1)")
    soak.add_argument("--batch-interval-s", type=float, default=0.0, help="delay between batch dispatches")
    soak.add_argument(
        "--allow-parallel-serial",
        action="store_true",
        help="allow max-workers > 1 when soak hardware is serial (unsafe by default)",
    )

    report = sub.add_parser("report", help="show campaign report")
    report.add_argument("--file", default=None, help="path to report json file")

    validate = sub.add_parser("validate-config", help="validate config + safety/recovery constraints")
    validate.add_argument("--config", default="configs/default.yaml", help="base config path")
    validate.add_argument("--template", default=None, help="campaign template yaml path")
    validate.add_argument("--target", default="stm32f3", help="target profile name")
    validate.add_argument(
        "--config-mode",
        choices=["strict", "legacy"],
        default="strict",
        help="config validation mode (default: strict)",
    )

    plugins = sub.add_parser("list-plugins", help="list plugin manifests")
    plugins.add_argument("--kind", default=None, help="filter by plugin kind")
    plugins.add_argument("--plugin-dir", action="append", default=[], help="extra plugin manifest directory")

    benchmark = sub.add_parser("benchmark", help="compare algorithms on the same campaign template")
    benchmark.add_argument("--config", default="configs/default.yaml", help="base config path")
    benchmark.add_argument("--template", default=None, help="campaign template yaml path")
    benchmark.add_argument("--target", default="stm32f3", help="target profile name")
    benchmark.add_argument("--algorithms", default="bayesian,rl", help="comma-separated algorithms")
    benchmark.add_argument("--runs", type=int, default=5, help="runs per algorithm")
    benchmark.add_argument("--trials", type=int, default=200, help="trials per run")
    benchmark.add_argument("--bo-backend", choices=["auto", "heuristic", "botorch", "turbo", "qnehvi"], default="auto")
    benchmark.add_argument("--objective", choices=["single", "multi"], default="single")
    benchmark.add_argument("--hardware", choices=["mock", "serial"], default=None)
    benchmark.add_argument("--serial-port", default=None)
    benchmark.add_argument("--serial-timeout", type=float, default=None)
    benchmark.add_argument("--serial-io", choices=["sync", "async"], default=None)
    benchmark.add_argument("--rl-backend", choices=["lite", "sb3"], default=None)
    benchmark.add_argument("--require-preflight", action="store_true")
    benchmark.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    benchmark.add_argument("--success-threshold", type=float, default=0.30)
    benchmark.add_argument("--run-tag", default=None)
    benchmark.add_argument("--plugin-dir", action="append", default=[])

    replay = sub.add_parser("replay", help="recompute summary from a trial JSONL log")
    replay.add_argument("--log", required=True, help="path to trial jsonl log")
    replay.add_argument("--report", default=None, help="optional report json to compare against")

    preflight = sub.add_parser("hil-preflight", help="run serial HIL preflight probe")
    preflight.add_argument("--config", default="configs/default.yaml", help="base config path")
    preflight.add_argument("--template", default=None, help="campaign template yaml path")
    preflight.add_argument("--target", default="stm32f3", help="target profile name")
    preflight.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    preflight.add_argument("--hardware", choices=["mock", "serial"], default=None)
    preflight.add_argument("--serial-port", default=None)
    preflight.add_argument("--serial-timeout", type=float, default=None)
    preflight.add_argument("--serial-io", choices=["sync", "async"], default=None)
    preflight.add_argument("--probe-trials", type=int, default=None)
    preflight.add_argument("--max-timeout-rate", type=float, default=None)
    preflight.add_argument("--max-reset-rate", type=float, default=None)
    preflight.add_argument("--max-p95-latency-s", type=float, default=None)
    preflight.add_argument("--output", default=None, help="optional preflight report output path")
    preflight.add_argument("--plugin-dir", action="append", default=[])

    train_rl = sub.add_parser("train-rl", help="train RL optimizer and emit checkpoint/report")
    train_rl.add_argument("--config", default="configs/default.yaml", help="base config path")
    train_rl.add_argument("--template", default=None, help="campaign template yaml path")
    train_rl.add_argument("--target", default="stm32f3", help="target profile name")
    train_rl.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    train_rl.add_argument("--rl-backend", choices=["lite", "sb3"], default="sb3")
    train_rl.add_argument("--steps", type=int, default=None, help="training steps override")
    train_rl.add_argument("--run-tag", default=None, help="optional run tag for report naming/metadata")
    train_rl.add_argument("--plugin-dir", action="append", default=[])

    eval_rl = sub.add_parser("eval-rl", help="evaluate RL checkpoint or current policy")
    eval_rl.add_argument("--config", default="configs/default.yaml", help="base config path")
    eval_rl.add_argument("--template", default=None, help="campaign template yaml path")
    eval_rl.add_argument("--target", default="stm32f3", help="target profile name")
    eval_rl.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    eval_rl.add_argument("--rl-backend", choices=["lite", "sb3"], default="sb3")
    eval_rl.add_argument("--episodes", type=int, default=50, help="evaluation episodes")
    eval_rl.add_argument("--checkpoint", default=None, help="optional checkpoint path to load")
    eval_rl.add_argument("--run-tag", default=None, help="optional run tag for report metadata")
    eval_rl.add_argument("--plugin-dir", action="append", default=[])

    return parser


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="configs/default.yaml", help="base config path")
    parser.add_argument("--template", default=None, help="campaign template yaml path")
    parser.add_argument(
        "--config-mode",
        choices=["strict", "legacy"],
        default="strict",
        help="config validation mode (default: strict)",
    )
    parser.add_argument("--target", default="stm32f3", help="target profile name (stm32f3, esp32)")
    parser.add_argument("--trials", type=int, default=None, help="number of campaign trials")
    parser.add_argument("--optimizer", choices=["bayesian", "rl"], default=None)
    parser.add_argument("--bo-backend", choices=["auto", "heuristic", "botorch", "turbo", "qnehvi"], default=None)
    parser.add_argument("--rl-backend", choices=["lite", "sb3"], default=None)
    parser.add_argument("--objective", choices=["single", "multi"], default=None)
    parser.add_argument("--enable-llm", action="store_true", help="enable LLM advisor fallback")
    parser.add_argument("--target-primitive", default=None, help="stop early when primitive is reached")
    parser.add_argument("--hardware", choices=["mock", "serial"], default=None)
    parser.add_argument("--serial-port", default=None, help="override serial target port")
    parser.add_argument("--serial-timeout", type=float, default=None, help="override serial timeout")
    parser.add_argument("--serial-io", choices=["sync", "async"], default=None, help="serial IO mode override")
    parser.add_argument(
        "--require-preflight",
        action="store_true",
        help="require serial HIL preflight pass before campaign run",
    )
    parser.add_argument("--rerun-count", type=int, default=None, help="repeat same campaign N times")
    parser.add_argument("--fixed-seed", type=int, default=None, help="base seed for reproducibility runs")
    parser.add_argument(
        "--success-threshold",
        type=float,
        default=None,
        help="threshold used in reproducibility aggregate",
    )
    parser.add_argument(
        "--plugin-dir",
        action="append",
        default=[],
        help="additional plugin manifest directory (repeatable)",
    )
    parser.add_argument("--run-tag", default=None, help="optional run tag for reproducibility tracking")


# ---------------------------------------------------------------------------
# Core campaign execution
# ---------------------------------------------------------------------------

def _run_campaign(args: argparse.Namespace) -> None:
    output = _execute_campaign(args)
    print(json.dumps(output, indent=2, ensure_ascii=False))


def _execute_campaign(args: argparse.Namespace) -> Dict[str, Any]:
    config, template_name = _load_run_config(args)
    config_mode = getattr(args, "config_mode", "strict")
    errors = _validate_runtime_config(config, mode=config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    preflight_result: Dict[str, Any] | None = None
    if bool(getattr(args, "require_preflight", False)):
        preflight_result = _run_hil_preflight_for_args(args, config=config, force=True)
        if preflight_result and not bool(preflight_result.get("valid", False)):
            report_path = preflight_result.get("report")
            raise SystemExit(f"HIL preflight failed. report={report_path}")

    run_tag = _resolve_run_tag(args, config)
    objective_mode = str(
        getattr(args, "objective", None)
        or config.get("optimizer", {}).get("bo", {}).get("objective_mode", "single")
    ).lower()
    if objective_mode not in {"single", "multi"}:
        objective_mode = "single"

    plugin_registry = _load_plugin_registry(config, getattr(args, "plugin_dir", []))

    trials = int(args.trials or config.get("experiment", {}).get("max_trials", 100))
    rerun_count = int(args.rerun_count or config.get("experiment", {}).get("rerun_count", 1))

    config_threshold = config.get("experiment", {}).get("success_threshold", 0.3)
    success_threshold = float(args.success_threshold if args.success_threshold is not None else config_threshold)

    default_seed = int(config.get("experiment", {}).get("seed", 42))
    fixed_seed = args.fixed_seed
    if fixed_seed is None:
        fixed_seed_cfg = config.get("experiment", {}).get("fixed_seed")
        fixed_seed = int(fixed_seed_cfg) if fixed_seed_cfg is not None else default_seed

    target_primitive = _parse_primitive(args.target_primitive)

    run_summaries: List[Dict[str, Any]] = []
    aggregate_report_path: str | None = None

    for run_index in range(rerun_count):
        run_seed = fixed_seed + run_index
        run_config = copy.deepcopy(config)
        run_config.setdefault("experiment", {})["seed"] = run_seed
        run_config.setdefault("logging", {})["run_tag"] = run_tag
        run_config.setdefault("optimizer", {}).setdefault("bo", {})["objective_mode"] = objective_mode
        run_config["_runtime_fingerprint"] = _runtime_fingerprint(
            config_hash_payload=run_config,
            store_enabled=bool(run_config.get("logging", {}).get("store_env_fingerprint", True)),
        )

        timestamp = datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")
        run_id = f"{timestamp}_{run_index + 1:02d}" if rerun_count > 1 else timestamp

        run_summary = _run_single_campaign(
            run_config=run_config,
            args=args,
            run_seed=run_seed,
            run_id=run_id,
            trials=trials,
            target_primitive=target_primitive,
            plugin_registry=plugin_registry,
        )
        run_summaries.append(run_summary)

    aggregate = _aggregate_rerun_results(run_summaries, success_threshold)

    if rerun_count > 1:
        aggregate_report = {
            "schema_version": 1,
            "created_at": datetime.now().isoformat(),
            "target": config.get("target", {}).get("name", args.target),
            "optimizer": args.optimizer or config.get("optimizer", {}).get("type", "bayesian"),
            "success_threshold": success_threshold,
            "runs": run_summaries,
            "aggregate": aggregate,
            "run_tag": run_tag,
        }
        aggregate_report_path = str(_write_json_report("repro", aggregate_report))

    output: Dict[str, Any] = {
        "schema_version": 1,
        "template": template_name,
        "rerun_count": rerun_count,
        "run_tag": run_tag,
        "objective_mode": objective_mode,
        "runs": run_summaries,
        "aggregate": aggregate,
    }
    if aggregate_report_path:
        output["aggregate_report"] = aggregate_report_path
    if preflight_result is not None:
        output["preflight"] = preflight_result

    return output


def _run_single_campaign(
    run_config: Dict[str, Any],
    args: argparse.Namespace,
    run_seed: int,
    run_id: str,
    trials: int,
    target_primitive: ExploitPrimitiveType | None,
    plugin_registry: PluginRegistry,
) -> Dict[str, Any]:
    optimizer_type = args.optimizer or run_config.get("optimizer", {}).get("type", "bayesian")
    param_space = run_config.get("glitch", {}).get("parameters", {})
    run_tag = _resolve_run_tag(args, run_config)

    optimizer = _create_optimizer(
        optimizer_type=optimizer_type,
        config=run_config,
        param_space=param_space,
        bo_backend=getattr(args, "bo_backend", None),
        rl_backend=getattr(args, "rl_backend", None),
    )

    observer = BasicObserver()
    classifier = RuleBasedClassifier()
    mapper = PrimitiveMapper()
    logger_viz = ExperimentLogger(run_id=run_id)
    mlflow_tracker = _create_mlflow_tracker(run_config)
    hardware = _create_hardware(args=args, config=run_config, seed=run_seed)
    llm = LLMAdvisor() if getattr(args, "enable_llm", False) else None
    safety_controller = SafetyController.from_config(run_config)
    recovery_executor = RecoveryExecutor.from_config(run_config)

    run_config["run_id"] = run_id
    run_config["run_tag"] = run_tag
    run_config.setdefault("target", run_config.get("target", {}))

    orchestrator = ExperimentOrchestrator(
        optimizer=optimizer,
        hardware=hardware,
        observer=observer,
        classifier=classifier,
        mapper=mapper,
        logger_viz=logger_viz,
        llm_advisor=llm,
        config=run_config,
        safety_controller=safety_controller,
        recovery_executor=recovery_executor,
    )

    mlflow_tracker.start_run(
        run_name=run_id,
        tags={
            "target": str(run_config.get("target", {}).get("name", "unknown")),
            "optimizer": str(optimizer_type),
            "run_tag": str(run_tag or "none"),
        },
        params={
            "seed": run_seed,
            "trials": trials,
            "run_tag": run_tag or "none",
        },
    )

    campaign = orchestrator.run_campaign(n_trials=trials, target_primitive=target_primitive)
    optimizer_telemetry = _snapshot_optimizer_telemetry(optimizer)
    summary_path = logger_viz.write_campaign_summary(
        campaign,
        mlflow_info=mlflow_tracker.snapshot(),
        optimizer_info=optimizer_telemetry,
    )
    manifest_path = logger_viz.write_run_manifest(run_config, plugin_snapshot=plugin_registry.snapshot())

    mlflow_tracker.log_metrics(
        {
            "success_rate": campaign.success_rate,
            "primitive_repro_rate": campaign.primitive_repro_rate,
            "runtime_total_seconds": campaign.runtime_total_seconds,
        },
        step=campaign.n_trials,
    )
    mlflow_tracker.log_artifact(summary_path)
    mlflow_tracker.log_artifact(manifest_path)
    mlflow_tracker.log_artifact(logger_viz.log_path)
    mlflow_tracker.end_run(status="FINISHED")

    return {
        "run_id": run_id,
        "seed": run_seed,
        "run_tag": run_tag,
        "campaign_id": campaign.campaign_id,
        "n_trials": campaign.n_trials,
        "success_rate": campaign.success_rate,
        "primitive_repro_rate": campaign.primitive_repro_rate,
        "time_to_first_primitive": campaign.time_to_first_primitive,
        "runtime_total_seconds": campaign.runtime_total_seconds,
        "error_breakdown": campaign.error_breakdown,
        "optimizer_backend": getattr(optimizer, "backend_in_use", optimizer_type),
        "optimizer_telemetry": optimizer_telemetry,
        "circuit_breaker": recovery_executor.breaker.snapshot(),
        "mlflow": mlflow_tracker.snapshot(),
        "report": str(summary_path),
        "manifest": str(manifest_path),
        "log": str(logger_viz.log_path),
    }


# ---------------------------------------------------------------------------
# Advanced execution modes: queue-run / soak / benchmark
# ---------------------------------------------------------------------------

def _queue_run(args: argparse.Namespace) -> None:
    queue_path = Path(args.queue)
    if not queue_path.exists():
        raise SystemExit(f"queue file not found: {queue_path}")
    if args.max_workers <= 0:
        raise SystemExit("--max-workers must be > 0")
    if args.job_interval_s < 0:
        raise SystemExit("--job-interval-s must be >= 0")
    if args.max_workers > 1 and not args.continue_on_error:
        raise SystemExit("queue parallel mode requires --continue-on-error")

    payload = yaml.safe_load(queue_path.read_text(encoding="utf-8")) or {}
    defaults = payload.get("defaults", {})
    jobs = payload.get("jobs", [])

    if not isinstance(jobs, list) or not jobs:
        raise SystemExit("queue yaml must include non-empty `jobs` list")

    prepared_jobs = _prepare_queue_jobs(jobs, respect_order=args.respect_order)
    if not prepared_jobs:
        raise SystemExit("queue has no executable jobs (all jobs disabled?)")

    if args.max_workers > 1 and _queue_has_serial_jobs(prepared_jobs, defaults) and not args.allow_parallel_serial:
        raise SystemExit("parallel serial queue is blocked by default; add --allow-parallel-serial to override")

    cli_overrides = {
        "config_mode": getattr(args, "config_mode", None),
        "serial_io": getattr(args, "serial_io", None),
        "rl_backend": getattr(args, "rl_backend", None),
        "require_preflight": bool(getattr(args, "require_preflight", False)),
        "run_tag": getattr(args, "run_tag", None),
    }

    checkpoint_file = _resolve_queue_checkpoint_path(args.checkpoint_file, queue_path)
    queue_digest = hashlib.sha256(queue_path.read_bytes()).hexdigest()
    checkpoint_data = _create_queue_checkpoint_template(queue_path, queue_digest)
    completed_keys: set[str] = set()

    if args.resume:
        loaded = _load_queue_checkpoint(checkpoint_file)
        if loaded:
            loaded_digest = str(loaded.get("queue_digest", ""))
            if loaded_digest and loaded_digest != queue_digest:
                raise SystemExit(
                    "checkpoint queue digest mismatch. queue file changed; start fresh or remove checkpoint."
                )
            checkpoint_data = loaded
            completed_keys = set(str(item) for item in loaded.get("completed_job_keys", []))

    order_lookup: Dict[str, int] = {}
    pending_items: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    for order_idx, item in enumerate(prepared_jobs):
        idx = int(item["index"])
        priority = int(item["priority"])
        job = item["job"]
        job_name = str(job.get("name", f"job_{idx}"))
        job_key = _queue_job_key(idx, job_name)
        order_lookup[job_key] = order_idx

        if job_key in completed_keys:
            results.append(
                {
                    "job_index": idx,
                    "job_name": job_name,
                    "priority": priority,
                    "status": "skipped_resume",
                    "_order": order_idx,
                }
            )
            continue

        pending_items.append(item)

    if args.max_workers == 1:
        for item in pending_items:
            job_key, record = _execute_queue_job(
                item=item,
                defaults=defaults,
                cli_plugin_dirs=args.plugin_dir,
                cli_overrides=cli_overrides,
            )
            record["_order"] = order_lookup[job_key]
            results.append(record)
            if record["status"] == "completed":
                completed_keys.add(job_key)
            _update_queue_checkpoint(
                checkpoint_data=checkpoint_data,
                checkpoint_file=checkpoint_file,
                completed_keys=completed_keys,
                job_key=job_key,
                job_name=record["job_name"],
                job_index=int(record["job_index"]),
                priority=int(record["priority"]),
                status=str(record["status"]),
                error=record.get("error"),
            )

            if args.job_interval_s > 0:
                time.sleep(args.job_interval_s)

            if record["status"] == "failed" and not args.continue_on_error:
                raise SystemExit(record.get("error", {}).get("message", "queue job failed"))
    else:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            future_map = {}
            for item in pending_items:
                future = executor.submit(
                    _execute_queue_job,
                    item=item,
                    defaults=defaults,
                    cli_plugin_dirs=args.plugin_dir,
                    cli_overrides=cli_overrides,
                )
                future_map[future] = item
                if args.job_interval_s > 0:
                    time.sleep(args.job_interval_s)

            for future in as_completed(future_map):
                job_key, record = future.result()
                record["_order"] = order_lookup[job_key]
                results.append(record)
                if record["status"] == "completed":
                    completed_keys.add(job_key)
                _update_queue_checkpoint(
                    checkpoint_data=checkpoint_data,
                    checkpoint_file=checkpoint_file,
                    completed_keys=completed_keys,
                    job_key=job_key,
                    job_name=record["job_name"],
                    job_index=int(record["job_index"]),
                    priority=int(record["priority"]),
                    status=str(record["status"]),
                    error=record.get("error"),
                )

    results = sorted(results, key=lambda item: int(item.get("_order", 10**9)))
    for item in results:
        item.pop("_order", None)

    failed_jobs = [job for job in results if job.get("status") == "failed"]
    skipped_jobs = [job for job in results if job.get("status") == "skipped_resume"]

    summary = {
        "schema_version": 1,
        "queue": str(queue_path),
        "queue_digest": queue_digest,
        "run_tag": getattr(args, "run_tag", None),
        "checkpoint_file": str(checkpoint_file),
        "executed_jobs": len(results),
        "completed_jobs": len([job for job in results if job.get("status") == "completed"]),
        "failed_jobs": len(failed_jobs),
        "skipped_jobs": len(skipped_jobs),
        "jobs": results,
    }
    report_path = _write_json_report("queue", summary)
    summary["queue_report"] = str(report_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _soak_run(args: argparse.Namespace) -> None:
    if args.batch_trials <= 0:
        raise SystemExit("--batch-trials must be > 0")
    if args.duration_minutes <= 0 and args.max_batches is None:
        raise SystemExit("set positive --duration-minutes or provide --max-batches")
    if args.max_workers <= 0:
        raise SystemExit("--max-workers must be > 0")
    if args.batch_interval_s < 0:
        raise SystemExit("--batch-interval-s must be >= 0")
    if args.max_workers > 1 and not args.continue_on_error:
        raise SystemExit("soak parallel mode requires --continue-on-error")
    if args.max_workers > 1 and _is_serial_soak(args) and not args.allow_parallel_serial:
        raise SystemExit("parallel serial soak is blocked by default; add --allow-parallel-serial to override")

    soak_preflight: Dict[str, Any] | None = None
    if bool(getattr(args, "require_preflight", False)):
        soak_config, _ = _load_run_config(args)
        errors = _validate_runtime_config(soak_config, mode=getattr(args, "config_mode", "strict"))
        if errors:
            raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

        soak_preflight = _run_hil_preflight_for_args(args, config=soak_config, force=True)
        if soak_preflight and not bool(soak_preflight.get("valid", False)):
            report_path = soak_preflight.get("report")
            raise SystemExit(f"HIL preflight failed. report={report_path}")

    start_monotonic = time.monotonic()
    end_time = (
        start_monotonic + max(0.0, args.duration_minutes) * 60.0
        if args.duration_minutes > 0
        else float("inf")
    )
    max_batches = args.max_batches or 10**9
    base_seed = args.fixed_seed if args.fixed_seed is not None else 42

    checkpoint_file = _resolve_soak_checkpoint_path(args)
    soak_key = _build_soak_resume_key(args)
    checkpoint_data = _create_soak_checkpoint_template(args, soak_key)

    if args.resume:
        loaded = _load_soak_checkpoint(checkpoint_file)
        if loaded:
            if str(loaded.get("soak_key", "")) != soak_key:
                raise SystemExit(
                    "soak checkpoint mismatch. options changed; start fresh or use a different checkpoint-file."
                )
            checkpoint_data = loaded

    runs: List[Dict[str, Any]] = list(checkpoint_data.get("runs", []))
    next_batch = len(runs)
    new_batches = 0

    while next_batch < max_batches:
        if new_batches > 0 and time.monotonic() >= end_time:
            break

        wave_size = min(int(args.max_workers), int(max_batches - next_batch))
        batch_indices = [next_batch + i for i in range(wave_size)]

        if args.max_workers == 1:
            batch_records = [
                _execute_soak_batch(
                    args=args,
                    batch_index=batch_indices[0],
                    base_seed=base_seed,
                    start_monotonic=start_monotonic,
                )
            ]
        else:
            with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
                future_map = {}
                for idx, batch_index in enumerate(batch_indices):
                    future = executor.submit(
                        _execute_soak_batch,
                        args=args,
                        batch_index=batch_index,
                        base_seed=base_seed,
                        start_monotonic=start_monotonic,
                    )
                    future_map[future] = batch_index
                    if args.batch_interval_s > 0 and idx < len(batch_indices) - 1:
                        time.sleep(args.batch_interval_s)

                batch_records = [future.result() for future in as_completed(future_map)]
                batch_records = sorted(batch_records, key=lambda item: int(item.get("batch", 0)))

        for record in batch_records:
            runs.append(record)
            new_batches += 1
            next_batch += 1
            _update_soak_checkpoint(checkpoint_data, checkpoint_file, runs, soak_key, next_batch + 1)
            if record.get("status") == "failed" and not args.continue_on_error:
                raise SystemExit(record.get("error", {}).get("message", "soak batch failed"))
            if args.batch_interval_s > 0 and args.max_workers == 1:
                time.sleep(args.batch_interval_s)

        if time.monotonic() >= end_time and new_batches >= 1:
            break

    completed_runs = [run for run in runs if run.get("status") == "completed"]
    aggregate = _aggregate_rerun_results(completed_runs, float(args.success_threshold or 0.3))
    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "mode": "soak",
        "checkpoint_file": str(checkpoint_file),
        "resumed": bool(args.resume),
        "run_tag": getattr(args, "run_tag", None),
        "objective_mode": getattr(args, "objective", None),
        "new_batches": new_batches,
        "batches": len(runs),
        "completed_batches": len(completed_runs),
        "failed_batches": len([run for run in runs if run.get("status") == "failed"]),
        "batch_trials": int(args.batch_trials),
        "duration_minutes": float(args.duration_minutes),
        "runs": runs,
        "aggregate": aggregate,
    }
    if soak_preflight is not None:
        payload["preflight"] = soak_preflight
    report_path = _write_json_report("soak", payload)
    payload["soak_report"] = str(report_path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _run_benchmark(args: argparse.Namespace) -> None:
    config, template_name = _load_run_config(args)
    errors = _validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    algorithms = [item.strip().lower() for item in args.algorithms.split(",") if item.strip()]
    invalid_algorithms = [algo for algo in algorithms if algo not in {"bayesian", "rl"}]
    if invalid_algorithms:
        raise SystemExit(f"unsupported algorithms: {', '.join(invalid_algorithms)}")

    plugin_registry = _load_plugin_registry(config, getattr(args, "plugin_dir", []))
    run_tag = _resolve_run_tag(args, config)
    objective_mode = str(getattr(args, "objective", "single")).lower()
    if objective_mode not in {"single", "multi"}:
        objective_mode = "single"

    results_by_algo: Dict[str, List[Dict[str, Any]]] = {algo: [] for algo in algorithms}
    base_seed = int(config.get("experiment", {}).get("fixed_seed") or config.get("experiment", {}).get("seed", 42))

    for algo_index, algo in enumerate(algorithms):
        for run_index in range(args.runs):
            run_seed = base_seed + run_index + (algo_index * 10000)
            run_id = f"bench_{algo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_index + 1:02d}"

            run_args = copy.copy(args)
            run_args.optimizer = algo
            run_args.enable_llm = False
            run_args.run_tag = run_tag
            run_args.objective = objective_mode
            run_config = copy.deepcopy(config)
            run_config.setdefault("experiment", {})["seed"] = run_seed
            run_config.setdefault("logging", {})["run_tag"] = run_tag
            run_config.setdefault("optimizer", {}).setdefault("bo", {})["objective_mode"] = objective_mode

            summary = _run_single_campaign(
                run_config=run_config,
                args=run_args,
                run_seed=run_seed,
                run_id=run_id,
                trials=int(args.trials),
                target_primitive=None,
                plugin_registry=plugin_registry,
            )
            results_by_algo[algo].append(summary)

    aggregate_by_algo = {
        algo: _aggregate_rerun_results(runs, success_threshold=float(args.success_threshold))
        for algo, runs in results_by_algo.items()
    }

    winner = max(
        aggregate_by_algo.items(),
        key=lambda item: (
            item[1].get("primitive_repro_rate_mean", 0.0),
            item[1].get("success_rate_mean", 0.0),
        ),
    )[0]

    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "algorithms": algorithms,
        "objective_mode": objective_mode,
        "run_tag": run_tag,
        "runs_per_algorithm": int(args.runs),
        "trials_per_run": int(args.trials),
        "results": results_by_algo,
        "aggregate": aggregate_by_algo,
        "winner": winner,
    }

    path = _write_json_report("comparison", payload)
    payload["comparison_report"] = str(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# RL train/eval utilities
# ---------------------------------------------------------------------------

def _train_rl_cmd(args: argparse.Namespace) -> None:
    config, template_name = _load_run_config(args)
    errors = _validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    run_tag = _resolve_run_tag(args, config)
    config = copy.deepcopy(config)
    config.setdefault("logging", {})["run_tag"] = run_tag
    param_space = config.get("glitch", {}).get("parameters", {})
    requested_backend = str(getattr(args, "rl_backend", "sb3"))
    rl_cfg = config.get("optimizer", {}).get("rl", {})
    total_steps = int(args.steps or rl_cfg.get("total_timesteps", 20_000))

    optimizer = _create_optimizer(
        optimizer_type="rl",
        config=config,
        param_space=param_space,
        bo_backend=None,
        rl_backend=requested_backend,
    )

    result: Dict[str, Any]
    if isinstance(optimizer, SB3Optimizer):
        result = optimizer.train(steps=total_steps)
    else:
        for _ in range(total_steps):
            params = optimizer.suggest()
            reward = _synthetic_reward(params)
            optimizer.observe(params, reward, context={"source": "offline_train"})
        result = {
            "schema_version": 1,
            "optimizer": "rl",
            "backend_requested": requested_backend,
            "backend_in_use": "lite",
            "steps_run": total_steps,
            "observed_steps": int(getattr(optimizer, "n_trials", total_steps)),
            "evaluation": {
                "episodes": min(100, total_steps),
                "mean_reward": _mean_reward_from_history(optimizer),
            },
        }

    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "run_tag": run_tag,
        "requested_backend": requested_backend,
        "result": result,
    }
    path = _write_json_report("rl_train", payload)
    payload["report"] = str(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _eval_rl_cmd(args: argparse.Namespace) -> None:
    config, template_name = _load_run_config(args)
    errors = _validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    run_tag = _resolve_run_tag(args, config)
    config = copy.deepcopy(config)
    config.setdefault("logging", {})["run_tag"] = run_tag
    requested_backend = str(getattr(args, "rl_backend", "sb3"))
    param_space = config.get("glitch", {}).get("parameters", {})

    optimizer = _create_optimizer(
        optimizer_type="rl",
        config=config,
        param_space=param_space,
        bo_backend=None,
        rl_backend=requested_backend,
    )

    checkpoint_loaded: str | None = None
    if args.checkpoint and isinstance(optimizer, SB3Optimizer):
        optimizer.load_checkpoint(args.checkpoint)
        checkpoint_loaded = str(args.checkpoint)

    if isinstance(optimizer, SB3Optimizer):
        evaluation = optimizer.evaluate(episodes=int(args.episodes))
        backend_in_use = optimizer.backend_in_use
    else:
        rewards = []
        for _ in range(max(1, int(args.episodes))):
            rewards.append(_synthetic_reward(optimizer.suggest()))
        evaluation = {
            "episodes": max(1, int(args.episodes)),
            "mean_reward": float(mean(rewards)) if rewards else 0.0,
            "min_reward": float(min(rewards)) if rewards else 0.0,
            "max_reward": float(max(rewards)) if rewards else 0.0,
        }
        backend_in_use = "lite"

    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "run_tag": run_tag,
        "requested_backend": requested_backend,
        "backend_in_use": backend_in_use,
        "checkpoint_loaded": checkpoint_loaded,
        "evaluation": evaluation,
    }
    path = _write_json_report("rl_eval", payload)
    payload["report"] = str(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Validation / Plugin / Replay
# ---------------------------------------------------------------------------

def _hil_preflight_cmd(args: argparse.Namespace) -> None:
    config, template_name = _load_run_config(args)
    errors = _validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    result = _run_hil_preflight_for_args(args, config=config, force=True)
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


def _run_hil_preflight_for_args(
    args: argparse.Namespace,
    *,
    config: Dict[str, Any] | None = None,
    force: bool = False,
) -> Dict[str, Any] | None:
    config_payload = config or _load_run_config(args)[0]
    hw_cfg = config_payload.get("hardware", {})
    mode = str(args.hardware or hw_cfg.get("mode", "mock")).lower()
    if mode != "serial":
        return None

    serial_cfg = hw_cfg.get("serial", {}) if isinstance(hw_cfg.get("serial", {}), dict) else {}
    preflight_cfg = serial_cfg.get("preflight", {}) if isinstance(serial_cfg.get("preflight", {}), dict) else {}
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
    hardware = _create_hardware(
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
            target_name=str(config_payload.get("target", {}).get("name", getattr(args, "target", "unknown"))),
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


def _build_preflight_safe_params(config: Dict[str, Any]) -> GlitchParameters:
    params_cfg = config.get("glitch", {}).get("parameters", {})

    width_cfg = params_cfg.get("width", {})
    offset_cfg = params_cfg.get("offset", {})
    voltage_cfg = params_cfg.get("voltage", {})
    repeat_cfg = params_cfg.get("repeat", {})

    width = (float(width_cfg.get("min", 0.0)) + float(width_cfg.get("max", 0.0))) / 2.0
    offset = (float(offset_cfg.get("min", 0.0)) + float(offset_cfg.get("max", 0.0))) / 2.0
    voltage_min = float(voltage_cfg.get("min", -1.0))
    voltage_max = float(voltage_cfg.get("max", 1.0))
    voltage = max(voltage_min, min(voltage_max, 0.0))
    repeat = int(max(int(repeat_cfg.get("min", 1)), 1))

    return GlitchParameters(
        width=width,
        offset=offset,
        voltage=voltage,
        repeat=repeat,
        ext_offset=0.0,
    )


def _resolve_preflight_output_path(path: str | None) -> Path | None:
    if path is None:
        return None
    return Path(path)


def _validate_config_cmd(args: argparse.Namespace) -> None:
    config, template_name = _load_run_config(args)
    plugin_registry = _load_plugin_registry(config, [])

    errors = _validate_runtime_config(config, mode=args.config_mode)
    payload = {
        "schema_version": 1,
        "template": template_name,
        "config_mode": args.config_mode,
        "valid": len(errors) == 0,
        "errors": errors,
        "plugin_count": len(plugin_registry.list()),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if errors:
        raise SystemExit(2)


def _list_plugins(args: argparse.Namespace) -> None:
    registry = _load_plugin_registry({}, getattr(args, "plugin_dir", []))
    manifests = [manifest.to_dict() for manifest in registry.list(kind=args.kind)]
    print(json.dumps({"schema_version": 1, "plugins": manifests}, indent=2, ensure_ascii=False))


def _replay_run(args: argparse.Namespace) -> None:
    log_path = Path(args.log)
    if not log_path.exists():
        raise SystemExit(f"log file not found: {log_path}")

    trials = _read_jsonl(log_path)
    replay_summary = summarize_trial_records(trials)

    output: Dict[str, Any] = {
        "schema_version": 1,
        "log": str(log_path),
        "replay_summary": replay_summary,
    }

    if args.report:
        report_path = Path(args.report)
        if not report_path.exists():
            raise SystemExit(f"report file not found: {report_path}")

        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        output["report"] = str(report_path)
        output["comparison"] = compare_summary_to_report(replay_summary, report_payload)

    print(json.dumps(output, indent=2, ensure_ascii=False))


def summarize_trial_records(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
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
    fault_dist: Dict[str, int] = {}
    primitive_dist: Dict[str, int] = {}
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


def compare_summary_to_report(summary: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _show_report(args: argparse.Namespace) -> None:
    report_file = Path(args.file) if args.file else _latest_report(Path("experiments/results"))
    if report_file is None or not report_file.exists():
        raise SystemExit("No report found. Run `autoglitch run` first.")

    with report_file.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _create_mlflow_tracker(config: Dict[str, Any]) -> MLflowTracker:
    logging_cfg = config.get("logging", {})
    nested_mlflow_cfg = logging_cfg.get("mlflow", {}) if isinstance(logging_cfg.get("mlflow", {}), dict) else {}

    enabled = bool(nested_mlflow_cfg.get("enabled", False))
    tracking_uri = (
        nested_mlflow_cfg.get("tracking_uri")
        or logging_cfg.get("mlflow_tracking_uri")
        or "mlruns"
    )
    experiment_name = str(nested_mlflow_cfg.get("experiment_name", "autoglitch"))

    return MLflowTracker(
        enabled=enabled,
        tracking_uri=str(tracking_uri) if tracking_uri else None,
        experiment_name=experiment_name,
    )


def _create_optimizer(
    optimizer_type: str,
    config: Dict[str, Any],
    param_space: Dict[str, Any],
    bo_backend: str | None,
    rl_backend: str | None,
):
    optimizer_cfg = config.get("optimizer", {})
    seed = int(config.get("experiment", {}).get("seed", 42))

    if optimizer_type == "rl":
        rl_cfg = optimizer_cfg.get("rl", {})
        backend = str(rl_backend or rl_cfg.get("backend", "lite")).lower()
        if backend == "sb3":
            return SB3Optimizer(
                param_space=param_space,
                seed=seed,
                algorithm=str(rl_cfg.get("algorithm", "ppo")),
                learning_rate=float(rl_cfg.get("learning_rate", 3e-4)),
                total_timesteps=int(rl_cfg.get("total_timesteps", 20_000)),
                train_interval=int(rl_cfg.get("train_interval", 32)),
                checkpoint_interval=int(rl_cfg.get("checkpoint_interval", 5_000)),
                warmup_steps=int(rl_cfg.get("warmup_steps", 256)),
                eval_interval=int(rl_cfg.get("eval_interval", 1_000)),
                save_best_only=bool(rl_cfg.get("save_best_only", False)),
                checkpoint_dir=str(rl_cfg.get("checkpoint_dir", "experiments/results")),
            )
        return RLOptimizer(
            param_space=param_space,
            seed=seed,
            algorithm=str(rl_cfg.get("algorithm", "ppo")),
            learning_rate=float(rl_cfg.get("learning_rate", 3e-4)),
        )

    bo_cfg = optimizer_cfg.get("bo", {})
    backend = bo_backend or str(bo_cfg.get("backend", "auto"))

    return BayesianOptimizer(
        param_space=param_space,
        seed=seed,
        n_initial=int(bo_cfg.get("n_initial", 50)),
        acquisition=str(bo_cfg.get("acquisition", "ei")),
        backend=backend,
        objective_mode=str(bo_cfg.get("objective_mode", "single")),
        multi_objective_weights={
            str(key): float(value)
            for key, value in (bo_cfg.get("multi_objective_weights", {}) or {}).items()
        },
        candidate_pool_size=int(bo_cfg.get("candidate_pool_size", 192)),
        vectorized_heuristic=bool(bo_cfg.get("vectorized_heuristic", True)),
    )


def _create_hardware(args: argparse.Namespace, config: Dict[str, Any], seed: int):
    hw_cfg = config.get("hardware", {})
    mode = args.hardware or hw_cfg.get("mode", "mock")

    if mode == "serial":
        from .hardware import AsyncSerialCommandHardware

        target_cfg = hw_cfg.get("target", {})
        port = args.serial_port or target_cfg.get("port")
        if not port:
            raise SystemExit("serial hardware mode requires a port (config.hardware.target.port or --serial-port)")

        timeout = float(args.serial_timeout if args.serial_timeout is not None else target_cfg.get("timeout", 1.0))
        serial_cfg = hw_cfg.get("serial", {}) if isinstance(hw_cfg.get("serial", {}), dict) else {}
        serial_io = str(getattr(args, "serial_io", None) or serial_cfg.get("io_mode", "sync")).lower()

        serial_template = hw_cfg.get(
            "serial_command_template",
            (
                "GLITCH width={width:.3f} offset={offset:.3f} "
                "voltage={voltage:.3f} repeat={repeat:d} ext_offset={ext_offset:.3f}"
            ),
        )

        adapter_kwargs = {
            "port": str(port),
            "baudrate": int(target_cfg.get("baudrate", 115200)),
            "timeout": timeout,
            "command_template": str(serial_template),
            "reset_command": str(hw_cfg.get("reset_command", "")),
            "trigger_command": str(hw_cfg.get("trigger_command", "")),
        }
        if serial_io == "async":
            return AsyncSerialCommandHardware(
                **adapter_kwargs,
                keep_open=bool(serial_cfg.get("keep_open", True)),
                reconnect_attempts=int(serial_cfg.get("reconnect_attempts", 2)),
                reconnect_backoff_s=float(serial_cfg.get("reconnect_backoff_s", 0.05)),
            )

        if serial_io != "sync":
            raise SystemExit(f"unsupported serial io mode: {serial_io} (expected sync or async)")

        return SerialCommandHardware(**adapter_kwargs)

    return MockHardware(seed=seed)


def _load_run_config(args: argparse.Namespace) -> tuple[Dict[str, Any], str | None]:
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


def _load_config(base_config_path: Path, target_name: str) -> Dict[str, Any]:
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


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_run_namespace(options: Dict[str, Any], cli_plugin_dirs: Iterable[str]) -> argparse.Namespace:
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
        objective=options.get("objective"),
        enable_llm=bool(options.get("enable_llm", False)),
        target_primitive=options.get("target_primitive"),
        hardware=options.get("hardware"),
        serial_port=options.get("serial_port"),
        serial_timeout=options.get("serial_timeout"),
        serial_io=options.get("serial_io"),
        require_preflight=bool(options.get("require_preflight", False)),
        rerun_count=options.get("rerun_count"),
        fixed_seed=options.get("fixed_seed"),
        success_threshold=options.get("success_threshold"),
        run_tag=options.get("run_tag"),
        plugin_dir=[*list(cli_plugin_dirs), *list(option_plugin_dirs)],
    )


def _prepare_queue_jobs(jobs: List[Dict[str, Any]], respect_order: bool) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
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

        prepared.append(
            {
                "index": idx,
                "priority": priority,
                "job": job,
            }
        )

    if respect_order:
        return prepared

    return sorted(prepared, key=lambda item: (-int(item["priority"]), int(item["index"])))


def _queue_has_serial_jobs(prepared_jobs: List[Dict[str, Any]], defaults: Dict[str, Any]) -> bool:
    for item in prepared_jobs:
        job = item["job"]
        merged = _deep_merge(defaults, job)
        mode = str(merged.get("hardware", "")).lower()
        if mode == "serial":
            return True
    return False


def _execute_queue_job(
    *,
    item: Dict[str, Any],
    defaults: Dict[str, Any],
    cli_plugin_dirs: Iterable[str],
    cli_overrides: Dict[str, Any] | None = None,
) -> tuple[str, Dict[str, Any]]:
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

    record: Dict[str, Any] = {
        "job_index": idx,
        "job_name": job_name,
        "priority": priority,
    }
    try:
        output = _execute_campaign(run_args)
        record["status"] = "completed"
        record["result"] = output
    except SystemExit as exc:
        record["status"] = "failed"
        record["error"] = {
            "type": "SystemExit",
            "message": str(exc),
            "code": exc.code,
        }
    except Exception as exc:
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


def _create_queue_checkpoint_template(queue_path: Path, queue_digest: str) -> Dict[str, Any]:
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


def _load_queue_checkpoint(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _update_queue_checkpoint(
    *,
    checkpoint_data: Dict[str, Any],
    checkpoint_file: Path,
    completed_keys: set[str],
    job_key: str,
    job_name: str,
    job_index: int,
    priority: int,
    status: str,
    error: Dict[str, Any] | None,
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
    return str(args.hardware or "").lower() == "serial"


def _execute_soak_batch(
    *,
    args: argparse.Namespace,
    batch_index: int,
    base_seed: int,
    start_monotonic: float,
) -> Dict[str, Any]:
    run_args = argparse.Namespace(
        config=args.config,
        template=args.template,
        config_mode=getattr(args, "config_mode", "strict"),
        target=args.target,
        trials=int(args.batch_trials),
        optimizer=args.optimizer,
        bo_backend=args.bo_backend,
        rl_backend=getattr(args, "rl_backend", None),
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
        output = _execute_campaign(run_args)
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
    except Exception as exc:
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


def _create_soak_checkpoint_template(args: argparse.Namespace, soak_key: str) -> Dict[str, Any]:
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


def _load_soak_checkpoint(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _update_soak_checkpoint(
    checkpoint_data: Dict[str, Any],
    checkpoint_file: Path,
    runs: List[Dict[str, Any]],
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


def _aggregate_rerun_results(run_summaries: List[Dict[str, Any]], success_threshold: float) -> Dict[str, Any]:
    success_rates = [float(run["success_rate"]) for run in run_summaries] if run_summaries else []
    repro_rates = [float(run["primitive_repro_rate"]) for run in run_summaries] if run_summaries else []

    primitive_trials = [run.get("time_to_first_primitive") for run in run_summaries]
    primitive_trials = [int(value) for value in primitive_trials if value is not None]

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


def _write_json_report(prefix: str, payload: Dict[str, Any], output_dir: Path = Path("experiments/results")) -> Path:
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


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


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


def _resolve_run_tag(args: argparse.Namespace, config: Dict[str, Any]) -> str | None:
    cli_tag = getattr(args, "run_tag", None)
    if cli_tag:
        return str(cli_tag)
    logging_tag = config.get("logging", {}).get("run_tag")
    if logging_tag:
        return str(logging_tag)
    return None


def _runtime_fingerprint(*, config_hash_payload: Dict[str, Any], store_enabled: bool) -> Dict[str, Any]:
    config_json = json.dumps(config_hash_payload, sort_keys=True, ensure_ascii=False)
    payload: Dict[str, Any] = {
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


def _safe_git_output(cmd: List[str]) -> str | None:
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None
    return output or None


def _load_plugin_registry(config: Dict[str, Any], cli_plugin_dirs: Iterable[str]) -> PluginRegistry:
    cfg_plugin_dirs = config.get("plugins", {}).get("manifest_dirs", [])
    all_dirs = [Path(path) for path in [*cfg_plugin_dirs, *cli_plugin_dirs] if path]
    return PluginRegistry.load_default(extra_dirs=all_dirs)


def _snapshot_optimizer_telemetry(optimizer: Any) -> Dict[str, Any]:
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


def _validate_runtime_config(config: Dict[str, Any], mode: str = "strict") -> List[str]:
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


if __name__ == "__main__":
    main()
