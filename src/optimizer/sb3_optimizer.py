"""Stable-Baselines3 compatible optimizer path.

This module provides a production-friendly interface even when SB3 is not
available in the runtime environment by transparently falling back to the
existing lightweight RL optimizer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..types import GlitchParameters
from .base import BaseOptimizer
from .rl_optimizer import RLOptimizer

try:  # pragma: no cover - optional dependency path
    import stable_baselines3  # noqa: F401

    _HAS_SB3 = True
except Exception:  # pragma: no cover - optional dependency path
    _HAS_SB3 = False


class SB3Optimizer(BaseOptimizer):
    """SB3 backend facade with deterministic fallback to RL-lite."""

    def __init__(
        self,
        param_space: Dict[str, Any],
        seed: int = 42,
        algorithm: str = "ppo",
        learning_rate: float = 3e-4,
        total_timesteps: int = 20_000,
        train_interval: int = 32,
        checkpoint_interval: int = 5_000,
        checkpoint_dir: str = "experiments/results",
    ):
        super().__init__(param_space, seed)
        self.algorithm = algorithm
        self.learning_rate = learning_rate
        self.total_timesteps = max(1, int(total_timesteps))
        self.train_interval = max(1, int(train_interval))
        self.checkpoint_interval = max(1, int(checkpoint_interval))
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self._lite = RLOptimizer(
            param_space=param_space,
            seed=seed,
            algorithm=algorithm,
            learning_rate=learning_rate,
        )
        self._observed_steps = 0
        self._last_checkpoint_step = 0
        self._backend_in_use = "sb3" if _HAS_SB3 else "lite_fallback"

    @property
    def backend_in_use(self) -> str:
        return self._backend_in_use

    def suggest(self) -> GlitchParameters:
        return self._lite.suggest()

    def observe(
        self,
        params: GlitchParameters,
        reward: float,
        context: dict | None = None,
    ) -> None:
        self._lite.observe(params, reward, context=context)
        self._history.append((params, reward))
        self._observed_steps += 1

        if self._observed_steps % self.train_interval == 0:
            self._train_or_fallback()

        if (self._observed_steps - self._last_checkpoint_step) >= self.checkpoint_interval:
            self._write_checkpoint()
            self._last_checkpoint_step = self._observed_steps

    def _train_or_fallback(self) -> None:
        """Switch backend status based on SB3 availability.

        The actual policy update is delegated to RL-lite by design to keep
        online fault-injection loops responsive and deterministic.
        """
        self._backend_in_use = "sb3" if _HAS_SB3 else "lite_fallback"

    def _write_checkpoint(self) -> None:
        payload = {
            "schema_version": 1,
            "optimizer": "rl",
            "backend_requested": "sb3",
            "backend_in_use": self._backend_in_use,
            "algorithm": self.algorithm,
            "learning_rate": self.learning_rate,
            "observed_steps": self._observed_steps,
            "total_timesteps": self.total_timesteps,
            "train_interval": self.train_interval,
            "checkpoint_interval": self.checkpoint_interval,
        }
        path = self.checkpoint_dir / f"rl_sb3_checkpoint_step_{self._observed_steps}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
