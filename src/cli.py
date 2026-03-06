"""AUTOGLITCH command line interface."""
from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Dict

from .cli_batch import queue_run, soak_run
from .cli_commands import (
    eval_rl_command,
    eval_suite_command,
    kb_ingest_command,
    kb_query_command,
    list_plugins_command,
    planner_step_command,
    replay_run_command,
    run_benchmark_command,
    show_report_command,
    train_rl_command,
    validate_config_command,
)
from .cli_execution import execute_campaign, run_single_campaign
from .cli_hardware import detect_hardware_command, doctor_hardware_command, setup_hardware_command
from .cli_parser import _build_parser
from .cli_preflight import hil_preflight_command, run_hil_preflight_for_args
from .cli_runtime import _create_hardware, _create_mlflow_tracker, _create_optimizer
from .cli_support import (
    _aggregate_rerun_results,
    _build_run_namespace,
    _deep_merge,
    _load_config,
    _load_run_config,
    _resolve_effective_hardware_mode,
    _validate_runtime_config,
    _write_json_report,
    compare_summary_to_report,
    summarize_trial_records,
)
from .orchestrator import ExperimentOrchestrator
from .plugins import PluginRegistry
from .types import ExploitPrimitiveType

logger = logging.getLogger(__name__)

__all__ = [
    "main",
    "_build_run_namespace",
    "_deep_merge",
    "_aggregate_rerun_results",
    "_load_config",
    "_load_run_config",
    "_resolve_effective_hardware_mode",
    "compare_summary_to_report",
    "summarize_trial_records",
]


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

    if args.command == "run-agentic":
        _run_agentic_cmd(args)
        return

    if args.command == "planner-step":
        _planner_step_cmd(args)
        return

    if args.command == "eval-suite":
        _eval_suite_cmd(args)
        return

    if args.command == "kb-ingest":
        _kb_ingest_cmd(args)
        return

    if args.command == "kb-query":
        _kb_query_cmd(args)
        return

    if args.command == "detect-hardware":
        _detect_hardware_cmd(args)
        return

    if args.command == "setup-hardware":
        _setup_hardware_cmd(args)
        return

    if args.command == "doctor-hardware":
        _doctor_hardware_cmd(args)
        return

    parser.print_help()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Core campaign execution
# ---------------------------------------------------------------------------

def _execute_campaign(args: argparse.Namespace) -> Dict[str, Any]:
    return execute_campaign(
        args,
        load_run_config=_load_run_config,
        validate_runtime_config=_validate_runtime_config,
        run_hil_preflight_for_args=_run_hil_preflight_for_args,
        run_single_campaign=_run_single_campaign,
    )


def _run_single_campaign(
    run_config: Dict[str, Any],
    args: argparse.Namespace,
    run_seed: int,
    run_id: str,
    trials: int,
    target_primitive: ExploitPrimitiveType | None,
    plugin_registry: PluginRegistry,
) -> Dict[str, Any]:
    return run_single_campaign(
        run_config=run_config,
        args=args,
        run_seed=run_seed,
        run_id=run_id,
        trials=trials,
        target_primitive=target_primitive,
        plugin_registry=plugin_registry,
        create_optimizer=_create_optimizer,
        create_mlflow_tracker=_create_mlflow_tracker,
        create_hardware=_create_hardware,
        orchestrator_cls=ExperimentOrchestrator,
    )


def _queue_run(args: argparse.Namespace) -> None:
    queue_run(
        args,
        execute_campaign=_execute_campaign,
        write_json_report=_write_json_report,
    )


def _soak_run(args: argparse.Namespace) -> None:
    soak_run(
        args,
        execute_campaign=_execute_campaign,
        load_run_config=_load_run_config,
        validate_runtime_config=_validate_runtime_config,
        run_hil_preflight_for_args=_run_hil_preflight_for_args,
        write_json_report=_write_json_report,
    )


def _hil_preflight_cmd(args: argparse.Namespace) -> None:
    hil_preflight_command(
        args,
        load_run_config=_load_run_config,
        validate_runtime_config=_validate_runtime_config,
        run_hil_preflight_for_args=_run_hil_preflight_for_args,
    )


def _run_hil_preflight_for_args(
    args: argparse.Namespace,
    *,
    config: Dict[str, Any] | None = None,
    force: bool = False,
) -> Dict[str, Any] | None:
    return run_hil_preflight_for_args(
        args,
        config=config,
        force=force,
        load_run_config=_load_run_config,
        create_hardware=_create_hardware,
    )


def _run_campaign(args: argparse.Namespace) -> None:
    output = _execute_campaign(args)
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Advanced execution modes: queue-run / soak / benchmark
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# RL train/eval utilities
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Agentic / Repro suite / Knowledge utilities
# ---------------------------------------------------------------------------

def _run_agentic_cmd(args: argparse.Namespace) -> None:
    if getattr(args, "ai_mode", None) is None:
        args.ai_mode = "agentic_enforced"
    _run_campaign(args)


# ---------------------------------------------------------------------------
# Extracted command wrappers
# ---------------------------------------------------------------------------

def _run_benchmark(args: argparse.Namespace) -> None:
    run_benchmark_command(args, run_single_campaign=_run_single_campaign)


def _train_rl_cmd(args: argparse.Namespace) -> None:
    train_rl_command(args)


def _eval_rl_cmd(args: argparse.Namespace) -> None:
    eval_rl_command(args)


def _planner_step_cmd(args: argparse.Namespace) -> None:
    planner_step_command(args)


def _eval_suite_cmd(args: argparse.Namespace) -> None:
    eval_suite_command(args, execute_campaign=_execute_campaign)


def _kb_ingest_cmd(args: argparse.Namespace) -> None:
    kb_ingest_command(args)


def _kb_query_cmd(args: argparse.Namespace) -> None:
    kb_query_command(args)


def _validate_config_cmd(args: argparse.Namespace) -> None:
    validate_config_command(args)


def _list_plugins(args: argparse.Namespace) -> None:
    list_plugins_command(args)


def _replay_run(args: argparse.Namespace) -> None:
    replay_run_command(args)


def _show_report(args: argparse.Namespace) -> None:
    show_report_command(args)


def _detect_hardware_cmd(args: argparse.Namespace) -> None:
    detect_hardware_command(
        args,
        load_run_config=_load_run_config,
        validate_runtime_config=_validate_runtime_config,
    )


def _setup_hardware_cmd(args: argparse.Namespace) -> None:
    setup_hardware_command(
        args,
        load_run_config=_load_run_config,
        validate_runtime_config=_validate_runtime_config,
    )


def _doctor_hardware_cmd(args: argparse.Namespace) -> None:
    doctor_hardware_command(
        args,
        load_run_config=_load_run_config,
        validate_runtime_config=_validate_runtime_config,
    )

# ---------------------------------------------------------------------------
# Validation / Plugin / Replay
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Agentic control
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    main()
