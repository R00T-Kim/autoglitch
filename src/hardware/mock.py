"""테스트/로컬 실행용 mock hardware."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..types import GlitchParameters, RawResult


@dataclass
class MockHardware:
    """글리치 파라미터 기반으로 확률적 결과를 생성하는 모의 장비."""

    seed: int = 42

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def execute(self, params: GlitchParameters) -> RawResult:
        score = self._fault_score(params)

        if score > 0.85:
            serial = b"AUTH BYPASS success: admin granted"
            error_code = None
            reset = False
        elif score > 0.7:
            serial = b"instruction skip detected near auth check"
            error_code = None
            reset = False
        elif score > 0.55:
            serial = b"checksum fail: data corruption"
            error_code = None
            reset = False
        elif score > 0.45:
            serial = b"hard fault exception"
            error_code = 1
            reset = False
        else:
            serial = b"boot ok"
            error_code = None
            reset = score < 0.1

        jitter = float(self._rng.uniform(0.0, 0.03))
        response_time = float(0.02 + 0.18 * (1.0 - score) + jitter)

        return RawResult(
            serial_output=serial,
            response_time=response_time,
            reset_detected=reset,
            error_code=error_code,
        )

    @staticmethod
    def _fault_score(params: GlitchParameters) -> float:
        # 실장비 대신 단순한 "sweet spot" 함수를 사용한다.
        width_norm = max(0.0, 1.0 - abs(params.width - 22.0) / 25.0)
        offset_norm = max(0.0, 1.0 - abs(params.offset - 16.0) / 20.0)
        voltage_norm = max(0.0, 1.0 - abs(params.voltage + 0.2) / 1.2)
        repeat_norm = max(0.0, min(1.0, params.repeat / 10.0))

        return float(
            0.35 * width_norm
            + 0.35 * offset_norm
            + 0.2 * voltage_norm
            + 0.1 * repeat_norm
        )
