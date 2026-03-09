"""ChipWhisperer-backed hardware adapter."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..types import GlitchParameters, RawResult
from .base import BaseHardwareAdapter

SerialFactory = Callable[..., object]


@dataclass
class ChipWhispererHardware(BaseHardwareAdapter):
    """Hardware adapter that drives a ChipWhisperer scope and optional UART target."""

    scope_name: str | None = None
    serial_number: str | None = None
    id_product: int | None = None
    bitstream: str | None = None
    force_programming: bool = False
    prog_speed_hz: int = 10_000_000
    default_setup: bool = True
    glitch_mode: str = "voltage"
    glitch_output: str = "glitch_only"
    trigger_src: str = "manual"
    target_serial_port: str | None = None
    target_baudrate: int = 115200
    target_timeout: float = 1.0
    capture_timeout_s: float = 0.25
    serial_factory: SerialFactory | None = None
    cw_module: Any | None = None

    adapter_id: str = "chipwhisperer-hardware"
    transport: str = "usb"

    def __post_init__(self) -> None:
        self._scope: Any | None = None
        self._target_serial: object | None = None

    def connect(self) -> None:
        if self._scope is not None:
            return
        cw = self._chipwhisperer()
        self._scope = self._open_scope(cw)
        self._configure_scope(self._scope)
        if self.target_serial_port:
            factory = self.serial_factory or _default_serial_factory
            self._target_serial = factory(
                self.target_serial_port,
                self.target_baudrate,
                timeout=self.target_timeout,
            )

    def disconnect(self) -> None:
        if self._target_serial is not None:
            close = getattr(self._target_serial, "close", None)
            if callable(close):
                close()
        self._target_serial = None
        if self._scope is not None:
            close = getattr(self._scope, "dis", None) or getattr(self._scope, "close", None)
            if callable(close):
                close()
        self._scope = None

    def healthcheck(self) -> dict[str, Any]:
        self.connect()
        assert self._scope is not None
        return {
            "ok": True,
            "adapter_id": self.adapter_id,
            "transport": self.transport,
            "scope_name": getattr(self._scope, "name", self.scope_name),
            "serial_number": self.serial_number
            or _scope_value(self._scope, ("sn", "serial_number", "serialNumber")),
            "target_serial_connected": self._target_serial is not None,
        }

    def get_capabilities(self) -> list[str]:
        return [
            "glitch.execute",
            "glitch.configure",
            "healthcheck",
            "trigger.manual",
            "target.serial",
        ]

    def trigger_target(self) -> None:
        self.connect()
        assert self._scope is not None
        manual_trigger = _scope_value(
            self._scope,
            (
                "glitch.manual_trigger",
                "glitch.manualTrigger",
            ),
        )
        if callable(manual_trigger):
            manual_trigger()

    def execute(self, params: GlitchParameters) -> RawResult:
        self.connect()
        assert self._scope is not None
        self._configure_glitch(params)

        target_serial = self._target_serial
        if target_serial is not None:
            reset_input = getattr(target_serial, "reset_input_buffer", None)
            if callable(reset_input):
                reset_input()

        start = time.perf_counter()
        capture_result: Any = None
        if self.trigger_src == "manual":
            self.trigger_target()
        else:
            arm = getattr(self._scope, "arm", None)
            if callable(arm):
                arm()
            capture = getattr(self._scope, "capture", None)
            if callable(capture):
                try:
                    capture_result = capture(timeout=self.capture_timeout_s)
                except TypeError:
                    capture_result = capture()

        serial_output = b""
        if target_serial is not None:
            serial_output = _read_target_serial(target_serial)
        response_time = time.perf_counter() - start

        capture_timeout = bool(capture_result) if isinstance(capture_result, (bool, int)) else False
        lowered = serial_output.lower()
        reset_detected = capture_timeout or b"reset" in lowered or b"reboot" in lowered
        error_code = 1 if capture_timeout else None

        return RawResult(
            serial_output=serial_output,
            response_time=float(response_time),
            reset_detected=reset_detected,
            error_code=error_code,
        )

    @classmethod
    def probe(
        cls,
        *,
        scope_name: str | None = None,
        serial_number: str | None = None,
        id_product: int | None = None,
        cw_module: Any | None = None,
    ) -> list[dict[str, Any]]:
        try:
            cw = cw_module or _default_chipwhisperer_module()
            devices: list[Any] = list(getattr(cw, "list_devices", lambda **kwargs: [])())
        except Exception:
            return []

        results: list[dict[str, Any]] = []
        for item in list(devices or []):
            parsed = _normalize_device_info(item)
            if scope_name and parsed.get("name") and str(parsed["name"]) != str(scope_name):
                continue
            if serial_number and parsed.get("sn") and str(parsed["sn"]) != str(serial_number):
                continue
            if id_product is not None and parsed.get("idProduct") not in {None, id_product}:
                continue
            results.append(parsed)
        return results

    def _chipwhisperer(self) -> Any:
        return self.cw_module or _default_chipwhisperer_module()

    def _open_scope(self, cw: Any) -> Any:
        kwargs: dict[str, Any] = {}
        if self.scope_name:
            kwargs["name"] = self.scope_name
        if self.serial_number:
            kwargs["sn"] = self.serial_number
        if self.id_product is not None:
            kwargs["idProduct"] = self.id_product
        try:
            return cw.scope(**kwargs)
        except TypeError:
            kwargs.pop("name", None)
            if self.scope_name:
                kwargs["scope_type"] = self.scope_name
            return cw.scope(**kwargs)

    def _configure_scope(self, scope: Any) -> None:
        if self.default_setup:
            default_setup = getattr(scope, "default_setup", None)
            if callable(default_setup):
                default_setup()
        if self.glitch_mode == "voltage":
            vglitch_setup = getattr(scope, "vglitch_setup", None)
            if callable(vglitch_setup):
                vglitch_setup()
        else:
            cglitch_setup = getattr(scope, "cglitch_setup", None)
            if callable(cglitch_setup):
                cglitch_setup()

        if self.bitstream:
            fpga = getattr(scope, "fpga", None)
            program = getattr(fpga, "FPGAProgram", None)
            if callable(program):
                program(self.bitstream, force=self.force_programming, prog_speed=self.prog_speed_hz)

        self._apply_glitch_attr("output", self.glitch_output)
        self._apply_glitch_attr("trigger_src", self.trigger_src)

    def _configure_glitch(self, params: GlitchParameters) -> None:
        self._apply_glitch_attr("offset", float(params.offset))
        self._apply_glitch_attr("width", float(params.width))
        self._apply_glitch_attr("repeat", int(params.repeat))
        self._apply_glitch_attr("ext_offset", float(params.ext_offset))

        io = getattr(self._scope, "io", None)
        if io is not None and hasattr(io, "glitch_lp"):
            io.glitch_lp = self.glitch_mode == "voltage"

    def _apply_glitch_attr(self, name: str, value: Any) -> None:
        assert self._scope is not None
        glitch = getattr(self._scope, "glitch", None)
        if glitch is None or not hasattr(glitch, name):
            return
        setattr(glitch, name, value)


def _scope_value(scope: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        current = scope
        valid = True
        for part in name.split("."):
            if current is None or not hasattr(current, part):
                valid = False
                break
            current = getattr(current, part)
        if valid:
            return current
    return None


def _normalize_device_info(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        payload = dict(item)
    else:
        payload = {}
        for key in ("name", "sn", "serial_number", "serialNumber", "idProduct", "idVendor"):
            value = getattr(item, key, None)
            if value is not None:
                payload[key] = value
    serial_number = payload.get("sn") or payload.get("serial_number") or payload.get("serialNumber")
    return {
        "name": payload.get("name"),
        "sn": serial_number,
        "idProduct": payload.get("idProduct"),
        "idVendor": payload.get("idVendor"),
        "raw": payload,
    }


def _read_target_serial(serial_obj: object) -> bytes:
    read_all = getattr(serial_obj, "read_all", None)
    if callable(read_all):
        data = bytes(read_all())
        if data:
            return data

    in_waiting = getattr(serial_obj, "in_waiting", 0)
    read = getattr(serial_obj, "read", None)
    if callable(read):
        size = int(in_waiting) if isinstance(in_waiting, int) and in_waiting > 0 else 4096
        return bytes(read(size))
    return b""


def _default_chipwhisperer_module() -> Any:
    try:
        import chipwhisperer as cw
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("chipwhisperer package is required for chipwhisperer-hardware") from exc
    return cw


def _default_serial_factory(port: str, baudrate: int, timeout: float) -> object:
    try:
        import serial
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("pyserial is required for ChipWhisperer target serial access") from exc
    return serial.Serial(port, baudrate=baudrate, timeout=timeout)
