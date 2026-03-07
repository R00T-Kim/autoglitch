"""RL-oriented AUTOGLITCH CLI command handlers."""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from statistics import mean
from typing import Any

from .cli_runtime import _create_optimizer
from .cli_support import (
    _load_run_config,
    _mean_reward_from_history,
    _resolve_run_tag,
    _synthetic_reward,
    _validate_runtime_config,
    _write_json_report,
)
from .optimizer import SB3Optimizer
from .types import (
    RLEvalReportPayload,
    RLEvaluationPayload,
    RLTrainReportPayload,
    RLTrainResultPayload,
)


def _coerce_rl_evaluation(payload: dict[str, Any]) -> RLEvaluationPayload:
    return {
        "episodes": max(1, int(payload.get("episodes", 1))),
        "mean_reward": float(payload.get("mean_reward", 0.0)),
        "min_reward": float(payload.get("min_reward", 0.0)),
        "max_reward": float(payload.get("max_reward", 0.0)),
    }


def _coerce_rl_train_result(
    payload: dict[str, Any],
    *,
    requested_backend: str,
) -> RLTrainResultPayload:
    evaluation_raw = payload.get("evaluation", {})
    evaluation = (
        _coerce_rl_evaluation(evaluation_raw)
        if isinstance(evaluation_raw, dict)
        else {
            "episodes": 1,
            "mean_reward": 0.0,
            "min_reward": 0.0,
            "max_reward": 0.0,
        }
    )
    return {
        "schema_version": int(payload.get("schema_version", 1)),
        "optimizer": str(payload.get("optimizer", "rl")),
        "backend_requested": str(payload.get("backend_requested", requested_backend)),
        "backend_in_use": str(payload.get("backend_in_use", "lite")),
        "steps_run": int(payload.get("steps_run", 0)),
        "observed_steps": int(payload.get("observed_steps", 0)),
        "checkpoint": str(payload["checkpoint"]) if payload.get("checkpoint") else None,
        "evaluation": evaluation,
    }


def train_rl_command(args: argparse.Namespace) -> None:
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

    result: RLTrainResultPayload
    if isinstance(optimizer, SB3Optimizer):
        result = _coerce_rl_train_result(
            optimizer.train(steps=total_steps),
            requested_backend=requested_backend,
        )
    else:
        for _ in range(total_steps):
            params = optimizer.suggest()
            reward = _synthetic_reward(params)
            optimizer.observe(params, reward, context={"source": "offline_train"})
        mean_reward = _mean_reward_from_history(optimizer)
        lite_evaluation: RLEvaluationPayload = {
            "episodes": min(100, total_steps),
            "mean_reward": mean_reward,
            "min_reward": mean_reward,
            "max_reward": mean_reward,
        }
        result = RLTrainResultPayload(
            schema_version=1,
            optimizer="rl",
            backend_requested=requested_backend,
            backend_in_use="lite",
            steps_run=total_steps,
            observed_steps=int(getattr(optimizer, "n_trials", total_steps)),
            checkpoint=None,
            evaluation=lite_evaluation,
        )

    payload: RLTrainReportPayload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "run_tag": run_tag,
        "requested_backend": requested_backend,
        "result": result,
        "report": "",
    }
    path = _write_json_report("rl_train", payload)
    payload["report"] = str(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def eval_rl_command(args: argparse.Namespace) -> None:
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
        evaluation = _coerce_rl_evaluation(optimizer.evaluate(episodes=int(args.episodes)))
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

    payload: RLEvalReportPayload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "run_tag": run_tag,
        "requested_backend": requested_backend,
        "backend_in_use": backend_in_use,
        "checkpoint_loaded": checkpoint_loaded,
        "evaluation": evaluation,
        "report": "",
    }
    path = _write_json_report("rl_eval", payload)
    payload["report"] = str(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
