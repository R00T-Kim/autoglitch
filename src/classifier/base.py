"""결함 분류기 기본 인터페이스"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from ..types import FaultClass, Observation


class BaseClassifier(ABC):
    """결함 분류기 추상 클래스"""

    @abstractmethod
    def classify(self, observation: Observation) -> FaultClass:
        """단일 관측 분류"""
        ...

    def classify_batch(self, observations: list[Observation]) -> list[FaultClass]:
        """배치 분류 (기본 구현: 순차)"""
        return [self.classify(obs) for obs in observations]

    @abstractmethod
    def get_confidence(self) -> float:
        """마지막 분류의 신뢰도"""
        ...


class RuleBasedClassifier(BaseClassifier):
    """규칙 기반 결함 분류기"""

    DEFAULT_RULES: dict[FaultClass, list[str]] = {
        FaultClass.AUTH_BYPASS: [
            "auth bypass",
            "bypass success",
            "admin granted",
            "unlock success",
            "privileged mode",
        ],
        FaultClass.INSTRUCTION_SKIP: [
            "instruction skip",
            "pc mismatch",
            "branch skipped",
            "skip detected",
        ],
        FaultClass.DATA_CORRUPTION: [
            "checksum fail",
            "crc error",
            "data corruption",
            "unexpected value",
            "memory mismatch",
        ],
    }

    def __init__(self, rules: dict[FaultClass, list[str]] | None = None):
        self.rules = rules or self.DEFAULT_RULES
        self._last_confidence = 0.0

    def classify(self, observation: Observation) -> FaultClass:
        """규칙 기반 분류"""
        raw = observation.raw

        if raw.reset_detected:
            self._last_confidence = 0.95
            return FaultClass.RESET

        if raw.response_time <= 0 or raw.error_code is not None:
            self._last_confidence = 0.9
            return FaultClass.CRASH

        serial_text = raw.serial_output.decode("utf-8", errors="ignore").lower()
        for fault_class, patterns in self.rules.items():
            if self._contains_pattern(serial_text, patterns):
                self._last_confidence = self._confidence_from_features(observation, boost=0.2)
                return fault_class

        if "fault" in serial_text or "exception" in serial_text:
            self._last_confidence = self._confidence_from_features(observation, boost=0.05)
            return FaultClass.UNKNOWN

        self._last_confidence = self._confidence_from_features(observation, boost=-0.2)
        return FaultClass.NORMAL

    def get_confidence(self) -> float:
        return self._last_confidence

    @staticmethod
    def _contains_pattern(text: str, patterns: Iterable[str]) -> bool:
        return any(pattern in text for pattern in patterns)

    @staticmethod
    def _confidence_from_features(observation: Observation, boost: float = 0.0) -> float:
        confidence = 0.7 + boost

        if observation.features.size >= 4:
            nonprintable_ratio = float(observation.features[3])
            confidence += min(nonprintable_ratio, 0.2)

        if observation.waveform is not None and observation.waveform.size > 0:
            confidence += 0.05

        return max(0.0, min(1.0, confidence))
