"""Reinforcement Learning 기반 글리치 파라미터 탐색."""

from __future__ import annotations

import logging
from dataclasses import fields
from typing import Any

import numpy as np

from ..types import GlitchParameters
from .base import BaseOptimizer

logger = logging.getLogger(__name__)


class GlitchEnv:
    """간단한 Gym-like 환경.

    실제 장비 대신 action<->parameter 변환과 상태 벡터 갱신 역할을 담당한다.
    """

    def __init__(self, param_space: dict[str, Any], seed: int = 42):
        self.param_space = param_space
        self._rng = np.random.default_rng(seed)
        self._step_count = 0
        self._param_fields = tuple(field.name for field in fields(GlitchParameters))

    def reset(self) -> np.ndarray:
        """환경 리셋"""
        self._step_count = 0
        return np.zeros(len(self._param_fields) + 1, dtype=float)

    def sample_action(self) -> np.ndarray:
        """[-1, 1] 범위 랜덤 action"""
        return self._rng.uniform(-1.0, 1.0, size=len(self._param_fields))

    def action_to_params(self, action: np.ndarray) -> GlitchParameters:
        values: dict[str, Any] = {}

        for idx, name in enumerate(self._param_fields):
            spec = self.param_space.get(name)
            if not isinstance(spec, dict):
                values[name] = getattr(GlitchParameters(0.0, 0.0), name)
                continue

            lower = float(spec.get("min", 0.0))
            upper = float(spec.get("max", lower))
            step = float(spec.get("step", 0.0))

            normalized = float(np.clip(action[idx], -1.0, 1.0))
            value = lower + ((normalized + 1.0) / 2.0) * (upper - lower)

            if step > 0:
                value = round(value / step) * step

            if name == "repeat" or all(
                isinstance(spec.get(k), int) for k in ("min", "max") if k in spec
            ):
                values[name] = int(round(value))
            else:
                values[name] = float(value)

        return GlitchParameters(**values)

    def step(self, action: np.ndarray):
        """한 스텝 실행 (예제용 시뮬레이션)."""
        self._step_count += 1
        params = self.action_to_params(action)

        # 간단한 보상: width/offset sweet-spot 근접도
        reward = max(0.0, 1.0 - abs(params.width - 20.0) / 30.0 - abs(params.offset - 15.0) / 30.0)
        done = False

        state = np.concatenate([params.to_array(), np.array([self._step_count], dtype=float)])
        info = {"params": params}
        return state, float(reward), done, info


class RLOptimizer(BaseOptimizer):
    """Stable-Baselines3 대체 가능한 lightweight RL optimizer."""

    def __init__(
        self,
        param_space: dict[str, Any],
        seed: int = 42,
        algorithm: str = "ppo",
        learning_rate: float = 3e-4,
    ):
        super().__init__(param_space, seed)
        self.algorithm = algorithm
        self.learning_rate = learning_rate
        self._agent: dict[str, Any] | None = None
        self._env: GlitchEnv | None = None
        self._rng = np.random.default_rng(seed)
        self._policy_mean: np.ndarray | None = None

    def suggest(self) -> GlitchParameters:
        """RL 정책(경험 기반 평균 + 탐험 잡음)으로 파라미터 제안"""
        if self._agent is None:
            self._init_agent()

        assert self._env is not None

        if self.n_trials < 8 or self._policy_mean is None:
            action = self._env.sample_action()
        else:
            noise_scale = max(0.05, min(0.4, 1.0 - self.learning_rate * 1000.0))
            action = self._policy_mean + self._rng.normal(
                0.0, noise_scale, size=self._policy_mean.shape
            )
            action = np.clip(action, -1.0, 1.0)

        return self._env.action_to_params(action)

    def observe(
        self,
        params: GlitchParameters,
        reward: float,
        context: dict | None = None,
    ) -> None:
        """관측을 history에 기록하고 정책 평균을 업데이트"""
        self._history.append((params, reward))

        if not self._history:
            return

        vectors = np.array([self._params_to_action(p) for p, _ in self._history], dtype=float)
        rewards = np.array([r for _, r in self._history], dtype=float)

        weights = rewards - rewards.min() + 1e-6
        if np.allclose(weights.sum(), 0.0):
            weights = np.ones_like(weights)

        self._policy_mean = np.average(vectors, axis=0, weights=weights)
        self._policy_mean = np.clip(self._policy_mean, -1.0, 1.0)

    def _init_agent(self) -> None:
        """환경/정책 초기화"""
        self._env = GlitchEnv(self.param_space, seed=self.seed)
        self._env.reset()
        self._agent = {
            "algorithm": self.algorithm,
            "learning_rate": self.learning_rate,
        }

    def _params_to_action(self, params: GlitchParameters) -> np.ndarray:
        assert self._env is not None

        values = []
        for name in (field.name for field in fields(GlitchParameters)):
            spec = self.param_space.get(name)
            value = float(getattr(params, name))

            if not isinstance(spec, dict):
                values.append(0.0)
                continue

            lower = float(spec.get("min", 0.0))
            upper = float(spec.get("max", lower + 1.0))

            if upper <= lower:
                values.append(0.0)
                continue

            normalized = ((value - lower) / (upper - lower)) * 2.0 - 1.0
            values.append(float(np.clip(normalized, -1.0, 1.0)))

        return np.array(values, dtype=float)
