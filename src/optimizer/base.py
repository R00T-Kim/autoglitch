"""최적화기 기본 인터페이스"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from ..types import GlitchParameters


class BaseOptimizer(ABC):
    """글리치 파라미터 최적화기 추상 클래스"""

    def __init__(self, param_space: Dict[str, Any], seed: int = 42):
        self.param_space = param_space
        self.seed = seed
        self._history: List[Tuple[GlitchParameters, float]] = []

    @abstractmethod
    def suggest(self) -> GlitchParameters:
        """다음 시도할 파라미터를 제안"""
        ...

    @abstractmethod
    def observe(
        self,
        params: GlitchParameters,
        reward: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """시도 결과를 관측하여 모델 업데이트"""
        ...

    def get_best(self) -> Optional[Tuple[GlitchParameters, float]]:
        """지금까지 최고 결과 반환"""
        if not self._history:
            return None
        return max(self._history, key=lambda x: x[1])

    @property
    def n_trials(self) -> int:
        return len(self._history)
