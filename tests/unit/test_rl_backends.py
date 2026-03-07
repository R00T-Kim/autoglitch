from __future__ import annotations

import json

from src.cli import _create_optimizer
from src.optimizer import RLOptimizer, SB3Optimizer

PARAM_SPACE = {
    "width": {"min": 0.0, "max": 50.0, "step": 0.1},
    "offset": {"min": 0.0, "max": 50.0, "step": 0.1},
    "voltage": {"min": -1.0, "max": 1.0},
    "repeat": {"min": 1, "max": 10},
}


def _base_config() -> dict:
    return {
        "experiment": {"seed": 123},
        "optimizer": {
            "rl": {
                "algorithm": "ppo",
                "learning_rate": 3e-4,
                "backend": "lite",
                "total_timesteps": 2000,
                "train_interval": 4,
                "checkpoint_interval": 8,
            }
        },
    }


def test_create_optimizer_uses_lite_backend_by_default() -> None:
    optimizer = _create_optimizer(
        optimizer_type="rl",
        config=_base_config(),
        param_space=PARAM_SPACE,
        bo_backend=None,
        rl_backend=None,
    )
    assert isinstance(optimizer, RLOptimizer)


def test_create_optimizer_uses_sb3_facade_when_requested() -> None:
    optimizer = _create_optimizer(
        optimizer_type="rl",
        config=_base_config(),
        param_space=PARAM_SPACE,
        bo_backend=None,
        rl_backend="sb3",
    )
    assert isinstance(optimizer, SB3Optimizer)
    assert optimizer.backend_in_use in {"sb3", "lite_fallback"}


def test_sb3_optimizer_train_and_eval_workflow(tmp_path) -> None:
    optimizer = _create_optimizer(
        optimizer_type="rl",
        config={
            **_base_config(),
            "optimizer": {
                "rl": {
                    "algorithm": "ppo",
                    "learning_rate": 3e-4,
                    "backend": "sb3",
                    "total_timesteps": 128,
                    "train_interval": 8,
                    "checkpoint_interval": 16,
                    "warmup_steps": 32,
                    "eval_interval": 16,
                    "save_best_only": False,
                    "checkpoint_dir": str(tmp_path),
                }
            },
        },
        param_space=PARAM_SPACE,
        bo_backend=None,
        rl_backend="sb3",
    )
    assert isinstance(optimizer, SB3Optimizer)

    train_result = optimizer.train(steps=32)
    assert train_result["observed_steps"] >= 32
    assert "checkpoint" in train_result

    eval_result = optimizer.evaluate(episodes=10)
    assert eval_result["episodes"] == 10
    assert 0.0 <= eval_result["mean_reward"] <= 1.0

    telemetry = optimizer.telemetry_snapshot()
    assert telemetry["backend_requested"] == "sb3"


def test_sb3_optimizer_checkpoint_roundtrip(tmp_path) -> None:
    optimizer = SB3Optimizer(param_space=PARAM_SPACE, checkpoint_dir=str(tmp_path))
    optimizer.train(steps=1)
    checkpoint_path = optimizer.save_checkpoint(tag="roundtrip")

    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    restored = optimizer.load_checkpoint(checkpoint_path)

    assert restored == payload
    assert restored["observed_steps"] == payload["observed_steps"]
    assert restored["observed_steps"] >= 1
    assert optimizer.telemetry_snapshot()["last_checkpoint_path"] == str(checkpoint_path)
