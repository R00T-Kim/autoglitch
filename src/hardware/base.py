"""Hardware interface abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from ..types import GlitchParameters, RawResult


class BaseHardwareAdapter(ABC):
    """Transport-agnostic hardware adapter contract."""

    adapter_id: str = "unknown"
    transport: str = "unknown"

    @abstractmethod
    def connect(self) -> None:
        """Connect to the backing device or service."""

    @abstractmethod
    def disconnect(self) -> None:
        """Release the backing device or service."""

    @abstractmethod
    def execute(self, params: GlitchParameters) -> RawResult:
        """Execute one glitch attempt and return raw result data."""

    def healthcheck(self) -> dict[str, Any]:
        return {"ok": True}

    def get_capabilities(self) -> list[str]:
        return []

    def reset_target(self) -> None:
        return None

    def trigger_target(self) -> None:
        return None


class BaseGlitcher(ABC):
    """글리처 장비 추상 인터페이스 (legacy contract)."""

    @abstractmethod
    def connect(self) -> None:
        """장비 연결"""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """장비 연결 해제"""
        ...

    @abstractmethod
    def configure(self, params: GlitchParameters) -> None:
        """글리치 파라미터 설정"""
        ...

    @abstractmethod
    def arm(self) -> None:
        """글리치 준비(arm)"""
        ...

    @abstractmethod
    def execute(self, params: GlitchParameters) -> RawResult:
        """글리치 실행 및 결과 반환"""
        ...

    @abstractmethod
    def disarm(self) -> None:
        """글리치 해제"""
        ...


class BaseTarget(ABC):
    """타깃 보드 추상 인터페이스"""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def reset(self) -> None:
        """타깃 리셋"""
        ...

    @abstractmethod
    def send_trigger(self) -> None:
        """트리거 신호 전송"""
        ...

    @abstractmethod
    def read_response(self, timeout: float = 1.0) -> bytes:
        """타깃 응답 읽기"""
        ...


class BaseScope(ABC):
    """오실로스코프 추상 인터페이스"""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def configure(self, sample_rate: int, duration: float) -> None: ...

    @abstractmethod
    def capture_waveform(self) -> np.ndarray:
        """파형 캡처"""
        ...
