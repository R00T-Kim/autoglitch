"""Runtime factory helpers for AUTOGLITCH CLI."""
from __future__ import annotations

import argparse
from typing import Any, Dict

from .hardware import MockHardware, SerialCommandHardware
from .logging_viz import MLflowTracker
from .optimizer import BayesianOptimizer, RLOptimizer, SB3Optimizer


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

        port_name = str(port)
        baudrate = int(target_cfg.get("baudrate", 115200))
        command_template = str(serial_template)
        reset_command = str(hw_cfg.get("reset_command", ""))
        trigger_command = str(hw_cfg.get("trigger_command", ""))

        if serial_io == "async":
            return AsyncSerialCommandHardware(
                port=port_name,
                baudrate=baudrate,
                timeout=timeout,
                command_template=command_template,
                reset_command=reset_command,
                trigger_command=trigger_command,
                keep_open=bool(serial_cfg.get("keep_open", True)),
                reconnect_attempts=int(serial_cfg.get("reconnect_attempts", 2)),
                reconnect_backoff_s=float(serial_cfg.get("reconnect_backoff_s", 0.05)),
            )

        if serial_io != "sync":
            raise SystemExit(f"unsupported serial io mode: {serial_io} (expected sync or async)")

        return SerialCommandHardware(
            port=port_name,
            baudrate=baudrate,
            timeout=timeout,
            command_template=command_template,
            reset_command=reset_command,
            trigger_command=trigger_command,
        )

    return MockHardware(seed=seed)
