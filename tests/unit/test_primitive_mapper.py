from __future__ import annotations

import numpy as np

from src.mapper import PrimitiveMapper
from src.types import (
    ExploitPrimitiveType,
    FaultClass,
    Observation,
    RawResult,
)


def test_mapper_selects_code_execution_for_auth_shell_signal() -> None:
    mapper = PrimitiveMapper()
    observation = Observation(
        raw=RawResult(
            serial_output=b"auth bypass success, shell exec available",
            response_time=0.04,
            reset_detected=False,
        ),
        features=np.array([0.04, 40.0, 0.0, 0.0, 0.0], dtype=float),
    )

    primitive = mapper.map(FaultClass.AUTH_BYPASS, observation)
    assert primitive.type == ExploitPrimitiveType.CODE_EXECUTION
    assert primitive.confidence > 0.8


def test_mapper_returns_none_for_unmapped_fault() -> None:
    mapper = PrimitiveMapper()
    observation = Observation(
        raw=RawResult(
            serial_output=b"normal",
            response_time=0.03,
            reset_detected=False,
        )
    )

    primitive = mapper.map(FaultClass.NORMAL, observation)
    assert primitive.type == ExploitPrimitiveType.NONE
    assert primitive.confidence == 0.0
