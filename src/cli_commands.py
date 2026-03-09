"""Extracted command handlers for the AUTOGLITCH CLI."""

from __future__ import annotations

import argparse
import copy
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .cli_commands_agentic import (
    eval_suite_command,
    kb_ingest_command,
    kb_query_command,
    planner_step_command,
)
from .cli_commands_rl import eval_rl_command, train_rl_command
from .cli_support import (
    _aggregate_rerun_results,
    _latest_report,
    _load_plugin_registry,
    _load_run_config,
    _read_jsonl,
    _resolve_ai_mode,
    _resolve_run_tag,
    _validate_runtime_config,
    _write_json_report,
    compare_summary_to_report,
    summarize_trial_records,
)
from .hardware import normalize_adapter_request

RunSingleCampaign = Callable[..., dict[str, Any]]

__all__ = [
    "eval_rl_command",
    "eval_suite_command",
    "kb_ingest_command",
    "kb_query_command",
    "list_plugins_command",
    "planner_step_command",
    "replay_run_command",
    "run_benchmark_command",
    "show_report_command",
    "train_rl_command",
    "validate_config_command",
]


def run_benchmark_command(
    args: argparse.Namespace,
    *,
    run_single_campaign: RunSingleCampaign,
) -> None:
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
    ai_mode = _resolve_ai_mode(args, config)
    objective_mode = str(getattr(args, "objective", "single")).lower()
    if objective_mode not in {"single", "multi"}:
        objective_mode = "single"
    benchmark_cfg = (
        config.get("benchmark", {}) if isinstance(config.get("benchmark", {}), dict) else {}
    )
    lab_cfg = config.get("lab", {}) if isinstance(config.get("lab", {}), dict) else {}
    backend_items = (
        getattr(args, "backends", None)
        or benchmark_cfg.get("backends")
        or [
            getattr(args, "hardware", None)
            or config.get("hardware", {}).get("adapter")
            or config.get("hardware", {}).get("mode", "mock")
        ]
    )
    if isinstance(backend_items, str):
        backend_items = [item.strip() for item in backend_items.split(",") if item.strip()]
    backends = [
        normalize_adapter_request(str(item)) or str(item)
        for item in backend_items
        if str(item).strip()
    ]
    if not backends:
        backends = ["mock-hardware"]
    benchmark_id = str(
        getattr(args, "benchmark_id", None)
        or benchmark_cfg.get("benchmark_id")
        or f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    benchmark_task = str(
        getattr(args, "benchmark_task", None) or benchmark_cfg.get("task", "det_fault")
    )
    lab_meta = {
        "operator": getattr(args, "operator", None) or lab_cfg.get("operator"),
        "board_id": getattr(args, "board_id", None) or lab_cfg.get("board_id"),
        "session_id": getattr(args, "session_id", None) or lab_cfg.get("session_id"),
        "wiring_profile": getattr(args, "wiring_profile", None) or lab_cfg.get("wiring_profile"),
        "board_prep_profile": getattr(args, "board_prep_profile", None)
        or lab_cfg.get("board_prep_profile"),
        "power_profile": getattr(args, "power_profile", None) or lab_cfg.get("power_profile"),
    }

    results_by_backend_algo: dict[str, dict[str, list[dict[str, Any]]]] = {
        backend: {algo: [] for algo in algorithms} for backend in backends
    }
    base_seed = int(
        config.get("experiment", {}).get("fixed_seed")
        or config.get("experiment", {}).get("seed", 42)
    )

    for backend_index, backend in enumerate(backends):
        for algo_index, algo in enumerate(algorithms):
            for run_index in range(args.runs):
                run_seed = base_seed + run_index + (algo_index * 10_000) + (backend_index * 100_000)
                run_id = (
                    f"bench_{benchmark_id}_{backend}_{algo}_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_index + 1:02d}"
                )

                run_args = copy.copy(args)
                run_args.optimizer = algo
                run_args.hardware = backend
                run_args.enable_llm = False
                run_args.run_tag = run_tag
                run_args.ai_mode = ai_mode
                run_args.objective = objective_mode
                run_args.benchmark_id = benchmark_id
                run_args.benchmark_task = benchmark_task
                run_config = copy.deepcopy(config)
                run_config.setdefault("experiment", {})["seed"] = run_seed
                run_config.setdefault("logging", {})["run_tag"] = run_tag
                run_config.setdefault("ai", {})["mode"] = ai_mode
                run_config.setdefault("optimizer", {}).setdefault("bo", {})["objective_mode"] = (
                    objective_mode
                )
                run_config.setdefault("hardware", {})["adapter"] = backend
                run_config["benchmark"] = {
                    "enabled": True,
                    "benchmark_id": benchmark_id,
                    "task": benchmark_task,
                    "backends": backends,
                    "backend": backend,
                    "operator": lab_meta.get("operator"),
                    "board_id": lab_meta.get("board_id"),
                    "session_id": lab_meta.get("session_id"),
                }
                run_config["lab"] = lab_meta

                summary = run_single_campaign(
                    run_config=run_config,
                    args=run_args,
                    run_seed=run_seed,
                    run_id=run_id,
                    trials=int(args.trials),
                    target_primitive=None,
                    plugin_registry=plugin_registry,
                )
                results_by_backend_algo[backend][algo].append(summary)

    aggregate_by_backend_algo = {
        backend: {
            algo: _aggregate_rerun_results(runs, success_threshold=float(args.success_threshold))
            for algo, runs in algo_results.items()
        }
        for backend, algo_results in results_by_backend_algo.items()
    }
    compare_cells: list[dict[str, Any]] = [
        {
            "backend": backend,
            "algorithm": algo,
            "aggregate": aggregate,
        }
        for backend, algo_results in aggregate_by_backend_algo.items()
        for algo, aggregate in algo_results.items()
    ]
    overall_winner: dict[str, Any] = max(
        compare_cells,
        key=lambda item: (
            float(item["aggregate"].get("primitive_repro_rate_mean", 0.0)),
            float(item["aggregate"].get("success_rate_mean", 0.0)),
            -float(item["aggregate"].get("infra_failure_rate_mean", 0.0)),
        ),
    )

    benchmark_payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "benchmark_id": benchmark_id,
        "task": benchmark_task,
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "backends": backends,
        "algorithms": algorithms,
        "ai_mode": ai_mode,
        "objective_mode": objective_mode,
        "run_tag": run_tag,
        "runs_per_algorithm": int(args.runs),
        "trials_per_run": int(args.trials),
        "lab": lab_meta,
        "results": results_by_backend_algo,
        "aggregate": aggregate_by_backend_algo,
    }
    benchmark_path = _write_json_report("benchmark", benchmark_payload)

    compare_payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "benchmark_id": benchmark_id,
        "target": config.get("target", {}).get("name", args.target),
        "task": benchmark_task,
        "run_tag": run_tag,
        "backends": backends,
        "algorithms": algorithms,
        "aggregate": aggregate_by_backend_algo,
        "overall_winner": overall_winner,
        "cells": compare_cells,
    }
    compare_path = _write_json_report("comparison", compare_payload)

    output = dict(benchmark_payload)
    output["benchmark_report"] = str(benchmark_path)
    output["comparison_report"] = str(compare_path)
    output["overall_winner"] = overall_winner
    print(json.dumps(output, indent=2, ensure_ascii=False))


def validate_config_command(args: argparse.Namespace) -> None:
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


def list_plugins_command(args: argparse.Namespace) -> None:
    registry = _load_plugin_registry({}, getattr(args, "plugin_dir", []))
    manifests = [manifest.to_dict() for manifest in registry.list(kind=args.kind)]
    print(json.dumps({"schema_version": 1, "plugins": manifests}, indent=2, ensure_ascii=False))


def replay_run_command(args: argparse.Namespace) -> None:
    log_path = Path(args.log)
    if not log_path.exists():
        raise SystemExit(f"log file not found: {log_path}")

    trials = _read_jsonl(log_path)
    replay_summary = summarize_trial_records(trials)

    output: dict[str, Any] = {
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


def show_report_command(args: argparse.Namespace) -> None:
    report_file = Path(args.file) if args.file else _latest_report(Path("experiments/results"))
    if report_file is None or not report_file.exists():
        raise SystemExit("No report found. Run `autoglitch run` first.")

    with report_file.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
