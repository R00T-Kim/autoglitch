"""LLM 기반 실험 자문 모듈 (휴리스틱 fallback 포함)."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from ..types import TrialResult

logger = logging.getLogger(__name__)


class LLMAdvisor:
    """LLM을 활용한 실험 설계 자문.

    실제 API 키가 없거나 모델 호출이 비활성일 때도
    규칙 기반 fallback 답변을 제공한다.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self._client = None  # Lazy init placeholder

    def suggest_search_strategy(
        self,
        target_info: dict | None = None,
        history: list[TrialResult] | None = None,
    ) -> dict[str, Any]:
        """탐색 전략 제안.

        Returns:
            dict with keys: focus_params, suggested_ranges, rationale
        """
        target_info = target_info or {}
        history = history or []

        focus_params = ["width", "offset", "voltage"]
        suggested_ranges = {
            "width": {"min": 5.0, "max": 35.0},
            "offset": {"min": 5.0, "max": 30.0},
            "voltage": {"min": -0.8, "max": 0.2},
        }

        if history:
            top_trials = sorted(
                history, key=lambda trial: trial.primitive.confidence, reverse=True
            )[:10]
            if top_trials:
                widths = [t.parameters.width for t in top_trials]
                offsets = [t.parameters.offset for t in top_trials]
                suggested_ranges["width"] = {"min": min(widths), "max": max(widths)}
                suggested_ranges["offset"] = {"min": min(offsets), "max": max(offsets)}

        family = str(target_info.get("family", "unknown"))
        rationale = f"{family} 타깃 기준으로 width/offset 중심 탐색 후 voltage 미세조정"

        return {
            "focus_params": focus_params,
            "suggested_ranges": suggested_ranges,
            "rationale": rationale,
        }

    def generate_hypothesis(self, recent_trials: list[TrialResult]) -> str:
        """최근 시도 결과를 기반으로 가설 생성"""
        if not recent_trials:
            return "최근 데이터가 없어 초기 랜덤 탐색 비중을 유지해야 합니다."

        fault_counter = Counter(trial.fault_class.name for trial in recent_trials)
        primitive_counter = Counter(trial.primitive.type.name for trial in recent_trials)

        dominant_fault, _ = fault_counter.most_common(1)[0]
        dominant_primitive, _ = primitive_counter.most_common(1)[0]

        return (
            f"최근 구간에서 {dominant_fault} 비율이 높습니다. "
            f"{dominant_primitive} 강화 가능성이 있어 width/offset 인근 영역 집중 탐색을 권장합니다."
        )

    def interpret_results(self, campaign_results: dict[str, Any]) -> str:
        """캠페인 결과 해석"""
        n_trials = campaign_results.get("n_trials", 0)
        success_rate = campaign_results.get("success_rate", 0.0)
        repro_rate = campaign_results.get("primitive_repro_rate", 0.0)

        return (
            f"총 {n_trials}회 실행에서 fault 성공률 {success_rate:.2%}, "
            f"primitive 재현률 {repro_rate:.2%}입니다. "
            "재현률이 낮으면 최고 성능 구간 주변의 탐색 폭을 줄이세요."
        )

    def suggest_priors(self, target_info: dict) -> dict[str, Any]:
        """타깃 정보 기반 BO prior 분포 제안"""
        family = str(target_info.get("family", "generic")).lower()

        if "xtensa" in family:
            width_mean, offset_mean = 18.0, 14.0
        elif "cortex" in family:
            width_mean, offset_mean = 22.0, 16.0
        else:
            width_mean, offset_mean = 20.0, 15.0

        return {
            "width": {"mean": width_mean, "std": 5.0},
            "offset": {"mean": offset_mean, "std": 4.0},
            "voltage": {"mean": -0.2, "std": 0.3},
            "repeat": {"mean": 3, "std": 2},
        }
