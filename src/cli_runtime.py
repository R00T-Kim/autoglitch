"""Runtime factory helpers for AUTOGLITCH CLI."""

from __future__ import annotations

import argparse
import copy
from typing import Any

from .hardware import (
    HardwareResolutionError,
    build_registry_from_config,
    normalize_adapter_request,
    resolve_hardware,
)
from .logging_viz import MLflowTracker
from .optimizer import BayesianOptimizer, RLOptimizer, SB3Optimizer


def _create_mlflow_tracker(config: dict[str, Any]) -> MLflowTracker:
    logging_cfg = config.get("logging", {})
    nested_mlflow_cfg = (
        logging_cfg.get("mlflow", {}) if isinstance(logging_cfg.get("mlflow", {}), dict) else {}
    )

    enabled = bool(nested_mlflow_cfg.get("enabled", False))
    tracking_uri = (
        nested_mlflow_cfg.get("tracking_uri") or logging_cfg.get("mlflow_tracking_uri") or "mlruns"
    )
    experiment_name = str(nested_mlflow_cfg.get("experiment_name", "autoglitch"))

    return MLflowTracker(
        enabled=enabled,
        tracking_uri=str(tracking_uri) if tracking_uri else None,
        experiment_name=experiment_name,
    )


def _create_optimizer(
    optimizer_type: str,
    config: dict[str, Any],
    param_space: dict[str, Any],
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


def _create_hardware(args: argparse.Namespace, config: dict[str, Any], seed: int):
    runtime_config = copy.deepcopy(config)
    registry = build_registry_from_config(runtime_config)
    hardware_cfg = runtime_config.setdefault("hardware", {})
    target_cfg = hardware_cfg.setdefault("target", {})
    serial_cfg = hardware_cfg.setdefault("serial", {})
    chipwhisperer_cfg = hardware_cfg.setdefault("chipwhisperer", {})
    requested_adapter = normalize_adapter_request(
        getattr(args, "hardware", None) or hardware_cfg.get("adapter") or hardware_cfg.get("mode")
    )
    if getattr(args, "serial_timeout", None) is not None:
        target_cfg["timeout"] = float(args.serial_timeout)
    if getattr(args, "serial_io", None) is not None:
        serial_cfg["io_mode"] = str(args.serial_io)
    if (
        getattr(args, "serial_port", None) is not None
        and requested_adapter == "chipwhisperer-hardware"
    ):
        chipwhisperer_cfg["target_serial_port"] = str(args.serial_port)
    try:
        resolution = resolve_hardware(
            config=runtime_config,
            explicit_adapter=getattr(args, "hardware", None),
            explicit_port=getattr(args, "serial_port", None),
            seed=seed,
            registry=registry,
            binding_file=getattr(args, "binding_file", None),
        )
    except HardwareResolutionError as exc:
        raise SystemExit(str(exc)) from exc

    hardware = registry.create(resolution.selected, runtime_config, seed)
    args.resolved_hardware_binding = resolution.selected.to_dict()
    args.resolved_hardware_source = resolution.source
    return hardware
