"""Core campaign execution helpers for the AUTOGLITCH CLI."""
from __future__ import annotations

import argparse
import copy
import logging
from datetime import datetime
from typing import Any, Callable

from .classifier import RuleBasedClassifier
from .cli_agentic import _run_campaign_agentic
from .cli_support import (
    _aggregate_rerun_results,
    _load_plugin_registry,
    _parse_primitive,
    _resolve_ai_mode,
    _resolve_policy_file,
    _resolve_run_tag,
    _runtime_fingerprint,
    _snapshot_optimizer_telemetry,
    _write_json_report,
)
from .hardware import hardware_binding_lock
from .llm_advisor import LLMAdvisor
from .logging_viz import ExperimentLogger
from .mapper import PrimitiveMapper
from .observer import BasicObserver
from .plugins import PluginRegistry
from .runtime import RecoveryExecutor
from .safety import SafetyController
from .types import ExploitPrimitiveType

logger = logging.getLogger(__name__)

LoadRunConfig = Callable[[argparse.Namespace], tuple[dict[str, Any], str | None]]
ValidateRuntimeConfig = Callable[..., list[str]]
RunHilPreflightForArgs = Callable[..., dict[str, Any] | None]
RunSingleCampaign = Callable[..., dict[str, Any]]
CreateOptimizer = Callable[..., Any]
CreateMlflowTracker = Callable[[dict[str, Any]], Any]
CreateHardware = Callable[..., Any]


def execute_campaign(
    args: argparse.Namespace,
    *,
    load_run_config: LoadRunConfig,
    validate_runtime_config: ValidateRuntimeConfig,
    run_hil_preflight_for_args: RunHilPreflightForArgs,
    run_single_campaign: RunSingleCampaign,
) -> dict[str, Any]:
    config, template_name = load_run_config(args)
    config_mode = getattr(args, "config_mode", "strict")
    errors = validate_runtime_config(config, mode=config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    preflight_result: dict[str, Any] | None = None
    if bool(getattr(args, "require_preflight", False)):
        preflight_result = run_hil_preflight_for_args(args, config=config, force=True)
        if preflight_result and not bool(preflight_result.get("valid", False)):
            report_path = preflight_result.get("report")
            raise SystemExit(f"HIL preflight failed. report={report_path}")

    run_tag = _resolve_run_tag(args, config)
    ai_mode = _resolve_ai_mode(args, config)
    policy_file = _resolve_policy_file(args, config)
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

    run_summaries: list[dict[str, Any]] = []
    aggregate_report_path: str | None = None

    for run_index in range(rerun_count):
        run_seed = fixed_seed + run_index
        run_config = copy.deepcopy(config)
        run_config.setdefault("experiment", {})["seed"] = run_seed
        run_config.setdefault("logging", {})["run_tag"] = run_tag
        run_config.setdefault("ai", {})["mode"] = ai_mode
        if policy_file:
            run_config.setdefault("ai", {})["policy_file"] = policy_file
        run_config.setdefault("optimizer", {}).setdefault("bo", {})["objective_mode"] = objective_mode
        run_config["_runtime_fingerprint"] = _runtime_fingerprint(
            config_hash_payload=run_config,
            store_enabled=bool(run_config.get("logging", {}).get("store_env_fingerprint", True)),
        )

        timestamp = datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")
        run_id = f"{timestamp}_{run_index + 1:02d}" if rerun_count > 1 else timestamp

        run_summary = run_single_campaign(
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
            "ai_mode": ai_mode,
        }
        aggregate_report_path = str(_write_json_report("repro", aggregate_report))

    output: dict[str, Any] = {
        "schema_version": 1,
        "template": template_name,
        "rerun_count": rerun_count,
        "run_tag": run_tag,
        "ai_mode": ai_mode,
        "objective_mode": objective_mode,
        "runs": run_summaries,
        "aggregate": aggregate,
    }
    if aggregate_report_path:
        output["aggregate_report"] = aggregate_report_path
    if preflight_result is not None:
        output["preflight"] = preflight_result

    return output



def run_single_campaign(
    *,
    run_config: dict[str, Any],
    args: argparse.Namespace,
    run_seed: int,
    run_id: str,
    trials: int,
    target_primitive: ExploitPrimitiveType | None,
    plugin_registry: PluginRegistry,
    create_optimizer: CreateOptimizer,
    create_mlflow_tracker: CreateMlflowTracker,
    create_hardware: CreateHardware,
    orchestrator_cls: type[Any],
) -> dict[str, Any]:
    optimizer_type = args.optimizer or run_config.get("optimizer", {}).get("type", "bayesian")
    param_space = run_config.get("glitch", {}).get("parameters", {})
    run_tag = _resolve_run_tag(args, run_config)

    optimizer = create_optimizer(
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
    mlflow_tracker = create_mlflow_tracker(run_config)
    hardware = create_hardware(args=args, config=run_config, seed=run_seed)
    llm = LLMAdvisor() if getattr(args, "enable_llm", False) else None
    safety_controller = SafetyController.from_config(run_config)
    recovery_executor = RecoveryExecutor.from_config(run_config)

    run_config["run_id"] = run_id
    run_config["run_tag"] = run_tag
    run_config.setdefault("target", run_config.get("target", {}))

    orchestrator = orchestrator_cls(
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
            "ai_mode": str(_resolve_ai_mode(args, run_config)),
        },
        params={
            "seed": run_seed,
            "trials": trials,
            "run_tag": run_tag or "none",
            "ai_mode": _resolve_ai_mode(args, run_config),
        },
    )
    mlflow_status = "FAILED"
    try:
        with hardware_binding_lock(getattr(args, "resolved_hardware_binding", None), timeout_s=0.0):
            ai_mode = _resolve_ai_mode(args, run_config)
            policy_file = _resolve_policy_file(args, run_config)
            if ai_mode == "off":
                campaign = orchestrator.run_campaign(n_trials=trials, target_primitive=target_primitive)
                agentic_meta = {
                    "mode": "off",
                    "events": [],
                    "policy_reject_count": 0,
                    "agentic_interventions": 0,
                    "trace_report": None,
                }
            else:
                campaign, agentic_meta = _run_campaign_agentic(
                    orchestrator=orchestrator,
                    optimizer=optimizer,
                    run_config=run_config,
                    n_trials=trials,
                    target_primitive=target_primitive,
                    ai_mode=ai_mode,
                    policy_file=policy_file,
                )

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
        mlflow_status = "FINISHED"

        return {
            "run_id": run_id,
            "seed": run_seed,
            "run_tag": run_tag,
            "ai_mode": ai_mode,
            "resolved_hardware_binding": getattr(args, "resolved_hardware_binding", None),
            "resolved_hardware_source": getattr(args, "resolved_hardware_source", None),
            "campaign_id": campaign.campaign_id,
            "n_trials": campaign.n_trials,
            "success_rate": campaign.success_rate,
            "primitive_repro_rate": campaign.primitive_repro_rate,
            "time_to_first_primitive": campaign.time_to_first_primitive,
            "runtime_total_seconds": campaign.runtime_total_seconds,
            "error_breakdown": campaign.error_breakdown,
            "optimizer_backend": getattr(optimizer, "backend_in_use", optimizer_type),
            "optimizer_telemetry": optimizer_telemetry,
            "agentic": agentic_meta,
            "circuit_breaker": recovery_executor.breaker.snapshot(),
            "mlflow": mlflow_tracker.snapshot(),
            "report": str(summary_path),
            "manifest": str(manifest_path),
            "log": str(logger_viz.log_path),
        }
    finally:
        try:
            mlflow_tracker.end_run(status=mlflow_status)
        except Exception:  # pragma: no cover - cleanup path
            logger.exception("failed to end MLflow run for %s", run_id)

        disconnect = getattr(hardware, "disconnect", None)
        if callable(disconnect):
            try:
                disconnect()
            except Exception:  # pragma: no cover - cleanup path
                logger.exception("failed to disconnect hardware for %s", run_id)
