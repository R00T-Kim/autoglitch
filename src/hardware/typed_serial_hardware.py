"""Typed JSONL serial hardware adapter."""

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
class TypedSerialCommandHardware(BaseHardwareAdapter):
    """Serial adapter that speaks the autoglitch.v1 JSONL control protocol."""

    port: str
    baudrate: int = 115200
    timeout: float = 1.0
    serial_factory: SerialFactory | None = None

    adapter_id: str = "serial-json-hardware"
    transport: str = "serial"

    def __post_init__(self) -> None:
        self._serial: object | None = None
        self._capabilities_cache: list[str] | None = None

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
        response = self._request({"command": "health"})
        return {
            "ok": bool(response.get("ok", response.get("status") == "ok")),
            "response": response,
        }

    def get_capabilities(self) -> list[str]:
        if self._capabilities_cache is not None:
            return list(self._capabilities_cache)
        response = self._request({"command": "capabilities"})
        capabilities = response.get("capabilities", [])
        if not isinstance(capabilities, list):
            capabilities = []
        self._capabilities_cache = [str(item) for item in capabilities]
        return list(self._capabilities_cache)

    def reset_target(self) -> None:
        self._request({"command": "reset"})

    def trigger_target(self) -> None:
        self._request({"command": "trigger"})

    def execute(self, params: GlitchParameters) -> RawResult:
        started = time.perf_counter()
        response = self._request(
            {
                "command": "execute",
                "payload": {
                    "width": float(params.width),
                    "offset": float(params.offset),
                    "voltage": float(params.voltage),
                    "repeat": int(params.repeat),
                    "ext_offset": float(params.ext_offset),
                },
            }
        )
        response_time = time.perf_counter() - started

        serial_output = str(response.get("serial_output", "")).encode("utf-8", errors="replace")
        reset_detected = bool(response.get("reset_detected", False))
        error_code_raw = response.get("error_code")
        error_code = int(error_code_raw) if isinstance(error_code_raw, int | float) else None

        return RawResult(
            serial_output=serial_output,
            response_time=float(response_time),
            reset_detected=reset_detected,
            error_code=error_code,
        )

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.connect()
        assert self._serial is not None

        self._write_json(payload)
        response = self._read_json()
        if str(response.get("status", "ok")).lower() not in {"ok", "success"}:
            raise RuntimeError(str(response.get("message", "typed serial command failed")))
        return response

    def _write_json(self, payload: dict[str, Any]) -> None:
        assert self._serial is not None
        write = getattr(self._serial, "write", None)
        if not callable(write):
            raise RuntimeError("serial object has no write()")
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        write(line)

    def _read_json(self) -> dict[str, Any]:
        assert self._serial is not None
        read_until = getattr(self._serial, "read_until", None)
        raw: bytes
        if callable(read_until):
            raw = bytes(read_until(b"\n"))
        else:
            read = getattr(self._serial, "read", None)
            if not callable(read):
                raise RuntimeError("serial object has no read/read_until")
            raw = bytes(read(4096))
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            raise RuntimeError("typed serial timeout or empty response")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"typed serial response is not valid JSON: {text!r}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("typed serial response must be a JSON object")
        return parsed

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
            write(json.dumps({"command": "hello"}, separators=(",", ":")).encode("utf-8") + b"\n")
            raw = bytes(read_until(b"\n")).decode("utf-8", errors="replace").strip()
            if not raw:
                return None
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return None
            if payload.get("protocol") != "autoglitch.v1":
                return None
            if str(payload.get("status", "ok")).lower() not in {"ok", "success"}:
                return None
            return {
                "confidence": 0.99,
                "reason": "typed_protocol_handshake_ok",
                "protocol": payload.get("protocol"),
                "adapter_id": payload.get("adapter_id", cls.adapter_id),
                "capabilities": payload.get("capabilities", []),
                "identity": payload.get("identity", {}),
            }
        except Exception:
            return None
        finally:
            if serial_obj is not None:
                close = getattr(serial_obj, "close", None)
                if callable(close):
                    close()


def _default_serial_factory(port: str, baudrate: int, timeout: float) -> object:
    try:
        import serial
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime environment
        raise RuntimeError("pyserial is required for typed serial hardware mode") from exc

    return serial.Serial(port, baudrate=baudrate, timeout=timeout)
