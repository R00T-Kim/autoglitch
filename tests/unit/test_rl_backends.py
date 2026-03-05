from __future__ import annotations

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
