"""Legacy text-protocol serial hardware adapter."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..types import GlitchParameters, RawResult
from .base import BaseHardwareAdapter

SerialFactory = Callable[..., object]


@dataclass
class SerialCommandHardware(BaseHardwareAdapter):
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
    serial_factory: SerialFactory | None = None

    adapter_id: str = "serial-command-hardware"
    transport: str = "serial"

    def __post_init__(self) -> None:
        self._serial: object | None = None

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

    def healthcheck(self) -> dict[str, Any]:
        response = self._read_command_response("HELLO")
        lowered = response.lower()
        ok = bool(response) and not lowered.startswith(b"err")
        return {
            "ok": ok,
            "protocol": "legacy-text",
            "response": response.decode("utf-8", errors="replace"),
        }

    def get_capabilities(self) -> list[str]:
        return ["glitch.execute", "target.reset", "target.trigger"]

    def reset_target(self) -> None:
        if self.reset_command:
            self._write_line(self.reset_command)

    def trigger_target(self) -> None:
        if self.trigger_command:
            self._write_line(self.trigger_command)

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
        error_code = (
            1
            if any(token in lowered for token in (b"err", b"fault", b"exception", b"panic"))
            else None
        )

        return RawResult(
            serial_output=response,
            response_time=float(response_time),
            reset_detected=reset_detected,
            error_code=error_code,
        )

    def _read_command_response(self, command: str) -> bytes:
        self.connect()
        self._write_line(command)
        return self._read_line()

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

    @classmethod
    def probe(
        cls,
        *,
        port: str,
        baudrate: int,
        timeout: float,
        serial_factory: SerialFactory | None = None,
    ) -> dict[str, Any] | None:
        serial_obj = None
        try:
            factory = serial_factory or _default_serial_factory
            serial_obj = factory(port, baudrate, timeout=timeout)
            write = getattr(serial_obj, "write", None)
            read_until = getattr(serial_obj, "read_until", None)
            if not callable(write) or not callable(read_until):
                return None
            write(b"HELLO\n")
            raw = bytes(read_until(b"\n")).strip()
            if not raw:
                return None
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("protocol") == "autoglitch.v1":
                return None
            lowered = raw.lower()
            if lowered.startswith(b"err"):
                return None
            if b"pong" not in lowered and b"hello" not in lowered and b"ok" not in lowered:
                return None
            return {
                "confidence": 0.88,
                "reason": "legacy_text_handshake_ok",
                "identity": {"banner": raw.decode("utf-8", errors="replace")},
            }
        except Exception:
            return None
        finally:
            if serial_obj is not None:
                close = getattr(serial_obj, "close", None)
                if callable(close):
                    close()


def _default_serial_factory(port: str, baudrate: int, timeout: float):
    try:
        import serial
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("pyserial is required for serial hardware mode") from exc

    return serial.Serial(port, baudrate=baudrate, timeout=timeout)
