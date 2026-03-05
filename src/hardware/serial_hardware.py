"""Serial 기반 실장비 어댑터."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from ..types import GlitchParameters, RawResult

SerialFactory = Callable[..., object]


@dataclass
class SerialCommandHardware:
    """시리얼 명령 기반 글리치 장비 어댑터.

    장비/펌웨어가 아래 형태의 텍스트 프로토콜을 지원한다고 가정한다.
    - GLITCH width=<..> offset=<..> voltage=<..> repeat=<..> ext_offset=<..>
    - 응답 한 줄(read_until) 반환
    """

    port: str
    baudrate: int = 115200
    timeout: float = 1.0
    command_template: str = (
        "GLITCH width={width:.3f} offset={offset:.3f} "
        "voltage={voltage:.3f} repeat={repeat:d} ext_offset={ext_offset:.3f}"
    )
    reset_command: str = ""
    trigger_command: str = ""
    serial_factory: Optional[SerialFactory] = None

    def __post_init__(self) -> None:
        self._serial = None

    def connect(self) -> None:
        if self._serial is not None:
            return

        factory = self.serial_factory or _default_serial_factory
        self._serial = factory(self.port, self.baudrate, timeout=self.timeout)

    def disconnect(self) -> None:
        if self._serial is not None:
            close = getattr(self._serial, "close", None)
            if callable(close):
                close()
        self._serial = None

    def execute(self, params: GlitchParameters) -> RawResult:
        self.connect()
        assert self._serial is not None

        start = time.perf_counter()

        if self.reset_command:
            self._write_line(self.reset_command)

        payload = self.command_template.format(
            width=params.width,
            offset=params.offset,
            voltage=params.voltage,
            repeat=params.repeat,
            ext_offset=params.ext_offset,
        )
        self._write_line(payload)

        if self.trigger_command:
            self._write_line(self.trigger_command)

        response = self._read_line()
        response_time = time.perf_counter() - start

        lowered = response.lower()
        reset_detected = (not response) or (b"reset" in lowered) or (b"reboot" in lowered)
        error_code = 1 if any(token in lowered for token in (b"err", b"fault", b"exception", b"panic")) else None

        return RawResult(
            serial_output=response,
            response_time=float(response_time),
            reset_detected=reset_detected,
            error_code=error_code,
        )

    def _write_line(self, message: str) -> None:
        assert self._serial is not None

        payload = message.rstrip("\n").encode("utf-8") + b"\n"
        write = getattr(self._serial, "write", None)
        if not callable(write):
            raise RuntimeError("serial object has no write()")
        write(payload)

    def _read_line(self) -> bytes:
        assert self._serial is not None

        read_until = getattr(self._serial, "read_until", None)
        if callable(read_until):
            return bytes(read_until(b"\n")).strip()

        read = getattr(self._serial, "read", None)
        if callable(read):
            return bytes(read(1024)).strip()

        raise RuntimeError("serial object has no read/read_until")


def _default_serial_factory(port: str, baudrate: int, timeout: float):
    try:
        import serial
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("pyserial is required for serial hardware mode") from exc

    return serial.Serial(port, baudrate=baudrate, timeout=timeout)
