"""Bayesian Optimization 기반 글리치 파라미터 탐색."""
from __future__ import annotations

import logging
from dataclasses import MISSING, fields
from typing import Any, Dict, Tuple

import numpy as np

from ..types import GlitchParameters
from .base import BaseOptimizer

logger = logging.getLogger(__name__)

try:
    import torch
    from botorch.acquisition import (
        ExpectedImprovement,
        ProbabilityOfImprovement,
        UpperConfidenceBound,
    )
    from botorch.fit import fit_gpytorch_mll
    from botorch.models import SingleTaskGP
    from botorch.optim import optimize_acqf
    from gpytorch.mlls import ExactMarginalLogLikelihood

    _HAS_BOTORCH = True
except Exception:  # pragma: no cover - optional dependency path
    _HAS_BOTORCH = False


class BayesianOptimizer(BaseOptimizer):
    """가벼운 surrogate 기반 Bayesian optimizer.

    - `backend=auto`: botorch 사용 가능 시 GP backend, 아니면 heuristic backend
    - `backend=botorch`: botorch 우선 시도(실패 시 heuristic fallback)
    - `backend=heuristic`: numpy 기반 kernel-regression surrogate만 사용
    """

    def __init__(
        self,
        param_space: Dict[str, Any],
        seed: int = 42,
        n_initial: int = 50,
        acquisition: str = "ei",
        backend: str = "auto",
        candidate_pool_size: int = 192,
    ):
        super().__init__(param_space, seed)
        self.n_initial = n_initial
        self.acquisition = acquisition.lower()
        self.backend_preference = backend.lower()
        self.candidate_pool_size = candidate_pool_size

        self._model = None
        self._rng = np.random.default_rng(seed)

        self._param_fields = tuple(field.name for field in fields(GlitchParameters))
        self._bounds = self._build_bounds(param_space)
        self._search_fields = tuple(name for name in self._param_fields if name in self._bounds)

        if not self._search_fields:
            raise ValueError("param_space must include at least one tunable parameter")

        self._backend_in_use = "heuristic"

    @property
    def backend_in_use(self) -> str:
        return self._backend_in_use

    def suggest(self) -> GlitchParameters:
        """다음 파라미터 제안: 초기에는 랜덤, 이후 acquisition 기반"""
        if self.n_trials < self.n_initial:
            return self._random_sample()

        if self._model is None or self.n_trials % 10 == 0:
            self._fit_model()

        return self._optimize_acquisition()

    def observe(
        self,
        params: GlitchParameters,
        reward: float,
        context: dict | None = None,
    ) -> None:
        """관측 결과 기록"""
        self._history.append((params, reward))

    def _random_sample(self) -> GlitchParameters:
        """파라미터 공간에서 랜덤 샘플링"""
        sampled: Dict[str, Any] = {}
        for name in self._search_fields:
            lower, upper, step, is_int = self._bounds[name]
            raw = self._rng.uniform(lower, upper)
            quantized = self._quantize(name, raw, step, is_int)
            quantized = max(lower, min(upper, float(quantized)))
            sampled[name] = int(round(quantized)) if (is_int or name == "repeat") else float(quantized)

        return self._build_params(sampled)

    def _fit_model(self) -> None:
        """backend 선택 후 surrogate model 학습"""
        if not self._history:
            self._model = None
            self._backend_in_use = "heuristic"
            return

        if self._should_try_botorch() and len(self._history) >= max(4, len(self._search_fields) + 1):
            try:
                self._fit_model_botorch()
                self._backend_in_use = "botorch"
                return
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning("botorch backend unavailable, fallback to heuristic: %s", exc)

        self._fit_model_heuristic()
        self._backend_in_use = "heuristic"

    def _fit_model_heuristic(self) -> None:
        xs = np.array([self._vectorize(params) for params, _ in self._history], dtype=float)
        ys = np.array([reward for _, reward in self._history], dtype=float)

        weights = ys - ys.min() + 1e-6
        if np.allclose(weights.sum(), 0.0):
            weights = np.ones_like(weights)

        mean = np.average(xs, axis=0, weights=weights)
        variance = np.average((xs - mean) ** 2, axis=0, weights=weights)

        self._model = {
            "backend": "heuristic",
            "xs": xs,
            "ys": ys,
            "mean": mean,
            "std": np.sqrt(np.maximum(variance, 1e-6)),
            "best_reward": float(ys.max()),
        }

    def _fit_model_botorch(self) -> None:
        assert _HAS_BOTORCH  # guarded by _should_try_botorch

        xs_np = np.array([self._vectorize(params) for params, _ in self._history], dtype=float)
        ys_np = np.array([reward for _, reward in self._history], dtype=float)

        train_x = torch.tensor(xs_np, dtype=torch.double)
        train_y = torch.tensor(ys_np, dtype=torch.double).unsqueeze(-1)

        model = SingleTaskGP(train_X=train_x, train_Y=train_y)
        mll = ExactMarginalLogLikelihood(model.likelihood, model)
        fit_gpytorch_mll(mll)

        self._model = {
            "backend": "botorch",
            "model": model,
            "train_x": train_x,
            "train_y": train_y,
            "best_reward": float(train_y.max().item()),
        }

    def _optimize_acquisition(self) -> GlitchParameters:
        """Acquisition 최적화로 다음 파라미터 선택"""
        if self._model is None:
            return self._random_sample()

        if self._backend_in_use == "botorch":
            candidate = self._optimize_acquisition_botorch()
            if candidate is not None:
                return candidate

        return self._optimize_acquisition_heuristic()

    def _optimize_acquisition_heuristic(self) -> GlitchParameters:
        if self._model is None or self._model.get("backend") != "heuristic":
            return self._random_sample()

        best_score = -np.inf
        best_params: GlitchParameters | None = None

        for _ in range(self.candidate_pool_size):
            candidate = self._random_sample()
            candidate_vec = self._vectorize(candidate)
            mu, uncertainty = self._predict_heuristic(candidate_vec)
            score = self._acquisition_score(mu, uncertainty)

            if score > best_score:
                best_score = score
                best_params = candidate

        return best_params or self._random_sample()

    def _optimize_acquisition_botorch(self) -> GlitchParameters | None:
        if not _HAS_BOTORCH or self._model is None or self._model.get("backend") != "botorch":
            return None

        model = self._model["model"]
        best_reward = float(self._model["best_reward"])

        try:
            bounds = self._torch_bounds()
            acqf = self._build_botorch_acquisition(model, best_reward)
            candidate, _ = optimize_acqf(
                acq_function=acqf,
                bounds=bounds,
                q=1,
                num_restarts=8,
                raw_samples=128,
            )
            vector = candidate.detach().cpu().numpy().reshape(-1)
            sampled = self._vector_to_sampled(vector)
            return self._build_params(sampled)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("botorch acquisition optimization failed: %s", exc)
            return None

    def _predict_heuristic(self, candidate_vec: np.ndarray) -> Tuple[float, float]:
        assert self._model is not None

        xs: np.ndarray = self._model["xs"]
        ys: np.ndarray = self._model["ys"]
        scaled_dist = np.linalg.norm((xs - candidate_vec) / (self._model["std"] + 1e-6), axis=1)

        kernel = np.exp(-scaled_dist)
        if np.allclose(kernel.sum(), 0.0):
            mu = float(np.mean(ys))
        else:
            mu = float(np.sum(kernel * ys) / np.sum(kernel))

        nearest = float(np.min(scaled_dist))
        uncertainty = max(0.0, min(1.0, nearest / 3.0))
        return mu, uncertainty

    def _acquisition_score(self, mu: float, uncertainty: float) -> float:
        best_reward = float(self._model["best_reward"]) if self._model else 0.0
        improvement = mu - best_reward

        if self.acquisition == "ucb":
            return mu + 0.6 * uncertainty

        if self.acquisition == "pi":
            temperature = max(0.05, uncertainty)
            return float(1.0 / (1.0 + np.exp(-(improvement / temperature))))

        # default: EI 근사 (exploit + explore)
        return improvement + 0.4 * uncertainty

    def _build_botorch_acquisition(self, model, best_reward: float):  # pragma: no cover - optional path
        if self.acquisition == "ucb":
            return UpperConfidenceBound(model=model, beta=0.2)
        if self.acquisition == "pi":
            return ProbabilityOfImprovement(model=model, best_f=best_reward)
        return ExpectedImprovement(model=model, best_f=best_reward)

    def _vectorize(self, params: GlitchParameters) -> np.ndarray:
        return np.array([float(getattr(params, name)) for name in self._search_fields], dtype=float)

    def _vector_to_sampled(self, vector: np.ndarray) -> Dict[str, Any]:
        sampled: Dict[str, Any] = {}
        for idx, name in enumerate(self._search_fields):
            lower, upper, step, is_int = self._bounds[name]
            quantized = self._quantize(name, float(vector[idx]), step, is_int)
            quantized = max(lower, min(upper, float(quantized)))
            sampled[name] = int(round(quantized)) if (is_int or name == "repeat") else float(quantized)
        return sampled

    def _torch_bounds(self):  # pragma: no cover - optional path
        assert _HAS_BOTORCH
        lows = [self._bounds[name][0] for name in self._search_fields]
        highs = [self._bounds[name][1] for name in self._search_fields]
        return torch.tensor([lows, highs], dtype=torch.double)

    def _build_params(self, sampled: Dict[str, Any]) -> GlitchParameters:
        values: Dict[str, Any] = {}
        for field in fields(GlitchParameters):
            if field.name in sampled:
                values[field.name] = sampled[field.name]
                continue

            if field.default is not MISSING:
                values[field.name] = field.default
            elif field.default_factory is not MISSING:  # type: ignore[attr-defined]
                values[field.name] = field.default_factory()
            else:
                values[field.name] = 0.0

        return GlitchParameters(**values)

    def _should_try_botorch(self) -> bool:
        if self.backend_preference == "heuristic":
            return False
        if not _HAS_BOTORCH:
            return False
        return self.backend_preference in {"auto", "botorch"}

    @staticmethod
    def _build_bounds(param_space: Dict[str, Any]) -> Dict[str, Tuple[float, float, float, bool]]:
        bounds: Dict[str, Tuple[float, float, float, bool]] = {}
        for name, spec in param_space.items():
            if not isinstance(spec, dict):
                continue

            lower = float(spec.get("min", 0.0))
            upper = float(spec.get("max", lower))
            step = float(spec.get("step", 0.0))
            is_int = all(isinstance(spec.get(k), int) for k in ("min", "max", "step") if k in spec)
            bounds[name] = (lower, upper, step, is_int)

        return bounds

    @staticmethod
    def _quantize(name: str, value: float, step: float, is_int: bool) -> Any:
        if step > 0:
            value = round(value / step) * step

        if is_int or name == "repeat":
            return int(round(value))

        return float(value)
