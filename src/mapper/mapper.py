"""Fault-to-Primitive 매퍼"""
from __future__ import annotations

from ..types import ExploitPrimitive, ExploitPrimitiveType, FaultClass, Observation


class PrimitiveMapper:
    """결함 클래스를 exploitable primitive로 매핑"""

    # 기본 매핑 테이블
    DEFAULT_MAPPING: dict[FaultClass, list[ExploitPrimitiveType]] = {
        FaultClass.INSTRUCTION_SKIP: [
            ExploitPrimitiveType.AUTH_CHECK_BYPASS,
            ExploitPrimitiveType.CONTROL_FLOW_HIJACK,
        ],
        FaultClass.DATA_CORRUPTION: [
            ExploitPrimitiveType.MEMORY_WRITE,
            ExploitPrimitiveType.PRIVILEGE_ESCALATION,
        ],
        FaultClass.AUTH_BYPASS: [
            ExploitPrimitiveType.AUTH_CHECK_BYPASS,
            ExploitPrimitiveType.CODE_EXECUTION,
        ],
        FaultClass.CRASH: [
            ExploitPrimitiveType.MEMORY_READ,
        ],
    }

    def __init__(self, mapping=None):
        self.mapping = mapping or self.DEFAULT_MAPPING

    def map(self, fault_class: FaultClass, observation: Observation) -> ExploitPrimitive:
        """결함 클래스 + 관측으로부터 exploit primitive 결정"""
        if fault_class not in self.mapping:
            return ExploitPrimitive(type=ExploitPrimitiveType.NONE, confidence=0.0)

        candidates = self.mapping[fault_class]
        if not candidates:
            return ExploitPrimitive(type=ExploitPrimitiveType.NONE, confidence=0.0)

        serial_text = observation.raw.serial_output.decode("utf-8", errors="ignore").lower()

        primary = self._choose_candidate(candidates, fault_class, serial_text)
        confidence = self._estimate_confidence(fault_class, observation, serial_text)

        return ExploitPrimitive(
            type=primary,
            confidence=confidence,
            description=f"mapped from {fault_class.name.lower()} via rule-based heuristic",
        )

    def _choose_candidate(
        self,
        candidates: list[ExploitPrimitiveType],
        fault_class: FaultClass,
        serial_text: str,
    ) -> ExploitPrimitiveType:
        if fault_class == FaultClass.AUTH_BYPASS and any(
            keyword in serial_text for keyword in ("shell", "exec", "command")
        ):
            return ExploitPrimitiveType.CODE_EXECUTION

        if fault_class == FaultClass.INSTRUCTION_SKIP:
            if any(keyword in serial_text for keyword in ("auth", "check", "verify")):
                return ExploitPrimitiveType.AUTH_CHECK_BYPASS
            return ExploitPrimitiveType.CONTROL_FLOW_HIJACK

        if fault_class == FaultClass.DATA_CORRUPTION:
            if any(keyword in serial_text for keyword in ("write", "overwrite", "store")):
                return ExploitPrimitiveType.MEMORY_WRITE
            return ExploitPrimitiveType.PRIVILEGE_ESCALATION

        return candidates[0]

    def _estimate_confidence(
        self,
        fault_class: FaultClass,
        observation: Observation,
        serial_text: str,
    ) -> float:
        """exploitability 신뢰도 추정"""
        base_confidence = {
            FaultClass.INSTRUCTION_SKIP: 0.7,
            FaultClass.DATA_CORRUPTION: 0.55,
            FaultClass.AUTH_BYPASS: 0.85,
            FaultClass.CRASH: 0.3,
        }

        confidence = base_confidence.get(fault_class, 0.0)

        if any(keyword in serial_text for keyword in ("success", "granted", "bypass")):
            confidence += 0.1

        if observation.features.size >= 2:
            response_time = float(observation.features[0])
            serial_len = float(observation.features[1])
            if response_time > 0:
                confidence += min(response_time / 100.0, 0.05)
            if serial_len > 0:
                confidence += min(serial_len / 200.0, 0.05)

        if observation.waveform is not None and observation.waveform.size > 0:
            confidence += 0.05

        return max(0.0, min(1.0, confidence))
