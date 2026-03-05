"""관측 데이터 수집/특징 추출."""
from __future__ import annotations

import numpy as np

from ..types import Observation, RawResult


class BasicObserver:
    """RawResult를 Observation으로 변환하는 기본 관측기."""

    def collect(self, raw_result: RawResult) -> Observation:
        text = raw_result.serial_output.decode("utf-8", errors="ignore")
        serial_len = len(text)
        non_printable = sum(1 for ch in text if not ch.isprintable())
        non_printable_ratio = (non_printable / serial_len) if serial_len else 0.0

        features = np.array(
            [
                float(raw_result.response_time),
                float(serial_len),
                1.0 if raw_result.reset_detected else 0.0,
                float(non_printable_ratio),
                1.0 if raw_result.error_code is not None else 0.0,
            ],
            dtype=float,
        )

        return Observation(raw=raw_result, features=features)
