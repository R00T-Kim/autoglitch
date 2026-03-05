"""AUTOGLITCH 핵심 데이터 타입 정의"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional

import numpy as np


class FaultClass(Enum):
    """결함 주입 결과 분류 taxonomy"""

    NORMAL = auto()
    RESET = auto()
    CRASH = auto()
    INSTRUCTION_SKIP = auto()
    DATA_CORRUPTION = auto()
    AUTH_BYPASS = auto()
    UNKNOWN = auto()


class ExploitPrimitiveType(Enum):
    """익스플로잇 가능한 프리미티브 타입"""

    CONTROL_FLOW_HIJACK = auto()
    AUTH_CHECK_BYPASS = auto()
    MEMORY_READ = auto()
    MEMORY_WRITE = auto()
    PRIVILEGE_ESCALATION = auto()
    CODE_EXECUTION = auto()
    NONE = auto()


@dataclass
class GlitchParameters:
    """글리치 파라미터"""

    width: float
    offset: float
    voltage: float = 0.0
    repeat: int = 1
    ext_offset: float = 0.0

    def to_array(self) -> np.ndarray:
        return np.array(
            [self.width, self.offset, self.voltage, self.repeat, self.ext_offset],
            dtype=float,
        )

    @classmethod
    def from_array(cls, arr: np.ndarray) -> "GlitchParameters":
        return cls(
            width=float(arr[0]),
            offset=float(arr[1]),
            voltage=float(arr[2]),
            repeat=int(arr[3]),
            ext_offset=float(arr[4]),
        )


@dataclass
class RawResult:
    """하드웨어로부터의 원시 결과"""

    serial_output: bytes
    response_time: float
    reset_detected: bool
    error_code: Optional[int] = None


@dataclass
class Observation:
    """전처리된 관측 결과"""

    raw: RawResult
    features: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    waveform: Optional[np.ndarray] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ExploitPrimitive:
    """익스플로잇 프리미티브"""

    type: ExploitPrimitiveType
    confidence: float = 0.0
    description: str = ""


@dataclass
class TrialResult:
    """단일 시도 결과"""

    trial_id: int
    parameters: GlitchParameters
    observation: Observation
    fault_class: FaultClass
    primitive: ExploitPrimitive
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CampaignResult:
    """실험 캠페인 전체 결과"""

    campaign_id: str
    trials: List[TrialResult] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_trials(self) -> int:
        return len(self.trials)

    @property
    def success_rate(self) -> float:
        """NORMAL/RESET/UNKNOWN을 제외한 fault 비율"""
        if not self.trials:
            return 0.0
        successes = sum(
            1
            for t in self.trials
            if t.fault_class not in (FaultClass.NORMAL, FaultClass.RESET, FaultClass.UNKNOWN)
        )
        return successes / len(self.trials)

    @property
    def fault_distribution(self) -> Dict[FaultClass, int]:
        dist: Dict[FaultClass, int] = {}
        for trial in self.trials:
            dist[trial.fault_class] = dist.get(trial.fault_class, 0) + 1
        return dist

    @property
    def primitive_distribution(self) -> Dict[ExploitPrimitiveType, int]:
        dist: Dict[ExploitPrimitiveType, int] = {}
        for trial in self.trials:
            primitive_type = trial.primitive.type
            if primitive_type == ExploitPrimitiveType.NONE:
                continue
            dist[primitive_type] = dist.get(primitive_type, 0) + 1
        return dist

    @property
    def time_to_first_primitive(self) -> Optional[int]:
        """첫 primitive 관측 trial id, 없으면 None"""
        for trial in self.trials:
            if trial.primitive.type != ExploitPrimitiveType.NONE:
                return trial.trial_id
        return None

    @property
    def primitive_repro_rate(self) -> float:
        """가장 많이 관측된 primitive의 재현 비율"""
        if not self.trials:
            return 0.0

        primitive_dist = self.primitive_distribution
        if not primitive_dist:
            return 0.0

        max_hits = max(primitive_dist.values())
        return max_hits / len(self.trials)
