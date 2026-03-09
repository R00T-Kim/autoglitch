"""Core campaign execution helpers for the AUTOGLITCH CLI."""

from __future__ import annotations

import argparse
import copy
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

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

DEFAULT_COMPONENT_PLUGINS = {
    "observer": "basic-observer",
    "classifier": "rule-classifier",
    "mapper": "primitive-mapper",
}


def _collect_lab_metadata(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    config_lab = config.get("lab", {}) if isinstance(config.get("lab", {}), dict) else {}
    return {
        "operator": getattr(args, "operator", None) or config_lab.get("operator"),
        "board_id": getattr(args, "board_id", None) or config_lab.get("board_id"),
        "session_id": getattr(args, "session_id", None) or config_lab.get("session_id"),
        "wiring_profile": getattr(args, "wiring_profile", None) or config_lab.get("wiring_profile"),
        "board_prep_profile": getattr(args, "board_prep_profile", None)
        or config_lab.get("board_prep_profile"),
        "power_profile": getattr(args, "power_profile", None) or config_lab.get("power_profile"),
    }


def _collect_benchmark_metadata(
    args: argparse.Namespace,
    config: dict[str, Any],
    *,
    backend: str | None = None,
) -> dict[str, Any]:
    config_benchmark = (
        config.get("benchmark", {}) if isinstance(config.get("benchmark", {}), dict) else {}
    )
    benchmark_id = getattr(args, "benchmark_id", None) or config_benchmark.get("benchmark_id")
    task = getattr(args, "benchmark_task", None) or config_benchmark.get("task")
    return {
        "enabled": bool(config_benchmark.get("enabled", False) or benchmark_id or task),
        "benchmark_id": benchmark_id,
        "task": task or "det_fault",
        "backend": backend
        or getattr(args, "hardware", None)
        or config.get("hardware", {}).get("adapter")
        or config.get("hardware", {}).get("mode"),
        "target": str(config.get("target", {}).get("name", getattr(args, "target", "unknown"))),
    }


def _hardware_resolution_snapshot(
    args: argparse.Namespace, config: dict[str, Any]
) -> dict[str, Any]:
    binding = getattr(args, "resolved_hardware_binding", None)
    if not isinstance(binding, dict):
        binding = {}
    return {
        "source": getattr(args, "resolved_hardware_source", None),
        "binding": binding,
        "target": str(config.get("target", {}).get("name", "unknown")),
    }


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
    success_threshold = float(
        args.success_threshold if args.success_threshold is not None else config_threshold
    )

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
        run_config.setdefault("optimizer", {}).setdefault("bo", {})["objective_mode"] = (
            objective_mode
        )
        run_config["lab"] = _collect_lab_metadata(args, run_config)
        run_config["benchmark"] = _collect_benchmark_metadata(args, run_config)
        if preflight_result is not None:
            run_config["_preflight_result"] = preflight_result
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


def _component_target_candidates(config: dict[str, Any]) -> set[str]:
    candidates: set[str] = set()
    target_cfg = config.get("target", {}) if isinstance(config.get("target", {}), dict) else {}
    hardware_target = config.get("hardware", {}).get("target", {})
    if isinstance(hardware_target, dict):
        target_type = hardware_target.get("type")
        if target_type:
            candidates.add(str(target_type).strip().lower())
    for value in (target_cfg.get("name"), target_cfg.get("family")):
        if value:
            candidates.add(str(value).strip().lower())
    return {item for item in candidates if item}


def _validate_component_target(
    *,
    component: str,
    plugin_name: str,
    manifest: Any,
    config: dict[str, Any],
) -> None:
    supported_targets = [
        str(item).strip().lower()
        for item in getattr(manifest, "supported_targets", [])
        if str(item).strip()
    ]
    if not supported_targets or "*" in supported_targets:
        return

    candidates = _component_target_candidates(config)
    if candidates and candidates.intersection(supported_targets):
        return

    target_name = str(config.get("target", {}).get("name", "unknown"))
    raise RuntimeError(
        f"{component} plugin {plugin_name} does not support target {target_name}. "
        f"supported_targets={supported_targets}"
    )


def _instantiate_runtime_components(
    *,
    config: dict[str, Any],
    plugin_registry: PluginRegistry,
) -> tuple[dict[str, str], Any, Any, Any]:
    components_cfg = (
        config.get("components", {}) if isinstance(config.get("components", {}), dict) else {}
    )
    selected_names: dict[str, str] = {}
    instances: dict[str, Any] = {}

    for component, kind in (
        ("observer", "observer"),
        ("classifier", "classifier"),
        ("mapper", "mapper"),
    ):
        plugin_name = str(components_cfg.get(component, DEFAULT_COMPONENT_PLUGINS[component]))
        manifest = plugin_registry.require(plugin_name, kind=kind)
        _validate_component_target(
            component=component,
            plugin_name=plugin_name,
            manifest=manifest,
            config=config,
        )
        instances[component] = plugin_registry.instantiate(plugin_name, kind=kind)
        selected_names[component] = plugin_name

    return selected_names, instances["observer"], instances["classifier"], instances["mapper"]


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

    component_plugins, observer, classifier, mapper = _instantiate_runtime_components(
        config=run_config,
        plugin_registry=plugin_registry,
    )
    logger_viz = ExperimentLogger(run_id=run_id)
    mlflow_tracker = create_mlflow_tracker(run_config)
    hardware = create_hardware(args=args, config=run_config, seed=run_seed)
    llm = LLMAdvisor() if getattr(args, "enable_llm", False) else None
    safety_controller = SafetyController.from_config(run_config)
    recovery_executor = RecoveryExecutor.from_config(run_config)

    run_config["run_id"] = run_id
    run_config["run_tag"] = run_tag
    run_config.setdefault("target", run_config.get("target", {}))
    run_config["_planner_backend"] = (
        "heuristic" if _resolve_ai_mode(args, run_config) != "off" else "disabled"
    )
    run_config["_advisor_backend"] = "heuristic" if llm is not None else "disabled"

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
            "observer": component_plugins["observer"],
            "classifier": component_plugins["classifier"],
            "mapper": component_plugins["mapper"],
        },
        params={
            "seed": run_seed,
            "trials": trials,
            "run_tag": run_tag or "none",
            "ai_mode": _resolve_ai_mode(args, run_config),
            "observer_plugin": component_plugins["observer"],
            "classifier_plugin": component_plugins["classifier"],
            "mapper_plugin": component_plugins["mapper"],
        },
    )
    mlflow_status = "FAILED"
    try:
        with hardware_binding_lock(getattr(args, "resolved_hardware_binding", None), timeout_s=0.0):
            ai_mode = _resolve_ai_mode(args, run_config)
            policy_file = _resolve_policy_file(args, run_config)
            if ai_mode == "off":
                campaign = orchestrator.run_campaign(
                    n_trials=trials, target_primitive=target_primitive
                )
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
            component_plugins=component_plugins,
            benchmark=run_config.get("benchmark", {}),
        )
        manifest_path = logger_viz.write_run_manifest(
            run_config, plugin_snapshot=plugin_registry.snapshot()
        )
        bundle_payload = logger_viz.write_artifact_bundle(
            summary_path=summary_path,
            manifest_path=manifest_path,
            log_path=logger_viz.log_path,
            preflight_report=run_config.get("_preflight_result"),
            hardware_resolution=_hardware_resolution_snapshot(args, run_config),
            benchmark=run_config.get("benchmark", {}),
            lab=run_config.get("lab", {}),
            component_plugins=component_plugins,
        )

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
        mlflow_tracker.log_artifact(bundle_payload["manifest"])
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
            "time_to_first_valid_fault": campaign.time_to_first_valid_fault,
            "time_to_first_primitive": campaign.time_to_first_primitive,
            "runtime_total_seconds": campaign.runtime_total_seconds,
            "error_breakdown": campaign.error_breakdown,
            "execution_status_breakdown": campaign.execution_status_breakdown,
            "infra_failure_count": campaign.infra_failure_count,
            "blocked_count": campaign.blocked_count,
            "fault_distribution": {
                fault.name: count for fault, count in campaign.fault_distribution.items()
            },
            "primitive_distribution": {
                primitive.name: count
                for primitive, count in campaign.primitive_distribution.items()
            },
            "optimizer_backend": getattr(optimizer, "backend_in_use", optimizer_type),
            "optimizer_telemetry": optimizer_telemetry,
            "component_plugins": component_plugins,
            "benchmark": run_config.get("benchmark", {}),
            "lab": run_config.get("lab", {}),
            "agentic": agentic_meta,
            "circuit_breaker": recovery_executor.breaker.snapshot(),
            "mlflow": mlflow_tracker.snapshot(),
            "report": str(summary_path),
            "manifest": str(manifest_path),
            "log": str(logger_viz.log_path),
            "artifact_bundle": bundle_payload["bundle_dir"],
            "bundle_manifest": bundle_payload["manifest"],
            "artifact_bundle_status": bundle_payload["completeness"],
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
