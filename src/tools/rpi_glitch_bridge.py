"""Raspberry Pi GPIO-based glitch bridge.

This bridge receives AUTOGLITCH line protocol commands over a control serial port
and translates them into GPIO pulses suitable for basic reset/trigger/crowbar control.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Optional, Protocol

from ..types import GlitchParameters
from .mock_glitch_bridge import parse_glitch_params


class GPIOBackend(Protocol):
    """Minimal GPIO backend contract."""

    def setup_output(self, pin: int, initial: bool) -> None: ...

    def setup_input(self, pin: int, pull_up: bool) -> None: ...

    def write(self, pin: int, value: bool) -> None: ...

    def read(self, pin: int) -> bool: ...

    def sleep(self, seconds: float) -> None: ...

    def cleanup(self) -> None: ...


class RPiGPIOBackend:
    """RPi.GPIO backend (BCM numbering)."""

    def __init__(self) -> None:
        try:
            import RPi.GPIO as gpio
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on target host
            raise RuntimeError("RPi.GPIO is required on Raspberry Pi bridge host") from exc

        self._gpio = gpio
        self._gpio.setwarnings(False)
        self._gpio.setmode(self._gpio.BCM)

    def setup_output(self, pin: int, initial: bool) -> None:
        self._gpio.setup(pin, self._gpio.OUT, initial=self._gpio.HIGH if initial else self._gpio.LOW)

    def setup_input(self, pin: int, pull_up: bool) -> None:
        pud = self._gpio.PUD_UP if pull_up else self._gpio.PUD_DOWN
        self._gpio.setup(pin, self._gpio.IN, pull_up_down=pud)

    def write(self, pin: int, value: bool) -> None:
        self._gpio.output(pin, self._gpio.HIGH if value else self._gpio.LOW)

    def read(self, pin: int) -> bool:
        return bool(self._gpio.input(pin))

    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(max(0.0, seconds))

    def cleanup(self) -> None:
        self._gpio.cleanup()


@dataclass
class RPiBridgeConfig:
    control_port: str
    control_baudrate: int = 115200
    control_timeout_s: float = 0.2
    glitch_pin: int = 18
    reset_pin: int | None = 23
    trigger_out_pin: int | None = 24
    trigger_in_pin: int | None = None
    active_high: bool = True
    reset_pulse_ms: float = 20.0
    inter_pulse_gap_us: float = 5.0
    wait_for_trigger: bool = False
    trigger_timeout_ms: float = 100.0
    max_width_us: float = 5000.0
    max_offset_us: float = 5_000_000.0
    max_repeat: int = 128
    target_uart_port: str | None = None
    target_uart_baudrate: int = 115200
    target_uart_timeout_s: float = 0.1


class RPiGlitchController:
    """GPIO pulse controller driven by line protocol commands."""

    def __init__(self, config: RPiBridgeConfig, gpio_backend: GPIOBackend) -> None:
        self.config = config
        self.gpio = gpio_backend
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return

        idle = self._idle_state()
        self.gpio.setup_output(self.config.glitch_pin, initial=idle)

        if self.config.reset_pin is not None:
            self.gpio.setup_output(self.config.reset_pin, initial=idle)

        if self.config.trigger_out_pin is not None:
            self.gpio.setup_output(self.config.trigger_out_pin, initial=idle)

        if self.config.trigger_in_pin is not None:
            self.gpio.setup_input(self.config.trigger_in_pin, pull_up=False)

        self._initialized = True

    def shutdown(self) -> None:
        if not self._initialized:
            return
        self.gpio.cleanup()
        self._initialized = False

    def handle_line(self, command_line: str, *, target_serial=None) -> bytes:
        self.initialize()
        line = command_line.strip()
        if not line:
            return b"ok"

        upper = line.upper()
        if upper in {"PING", "HELLO"}:
            return b"pong"

        if upper == "RESET":
            self.reset_target()
            return b"reset ok"

        if upper == "TRIGGER":
            self.trigger_once()
            return b"trigger ok"

        if upper.startswith("GLITCH "):
            params = parse_glitch_params(line)
            self.run_glitch(params)
            target_line = self._read_target_line(target_serial)
            if target_line:
                return target_line
            return b"glitch ok"

        return b"err unknown command"

    def run_glitch(self, params: GlitchParameters) -> None:
        self.initialize()
        self._validate_params(params)

        if self.config.wait_for_trigger and self.config.trigger_in_pin is not None:
            if not self._wait_for_trigger():
                raise RuntimeError("trigger timeout")

        if params.offset > 0:
            self.gpio.sleep(params.offset / 1_000_000.0)

        for idx in range(int(params.repeat)):
            self._set_glitch(active=True)
            self.gpio.sleep(params.width / 1_000_000.0)
            self._set_glitch(active=False)

            if idx < int(params.repeat) - 1:
                gap_us = params.ext_offset if params.ext_offset > 0 else self.config.inter_pulse_gap_us
                self.gpio.sleep(gap_us / 1_000_000.0)

    def reset_target(self) -> None:
        self.initialize()
        if self.config.reset_pin is None:
            raise RuntimeError("reset pin is not configured")
        self._set_pin(self.config.reset_pin, active=True)
        self.gpio.sleep(self.config.reset_pulse_ms / 1000.0)
        self._set_pin(self.config.reset_pin, active=False)

    def trigger_once(self) -> None:
        self.initialize()
        if self.config.trigger_out_pin is None:
            raise RuntimeError("trigger_out pin is not configured")
        self._set_pin(self.config.trigger_out_pin, active=True)
        self.gpio.sleep(self.config.reset_pulse_ms / 1000.0)
        self._set_pin(self.config.trigger_out_pin, active=False)

    def _validate_params(self, params: GlitchParameters) -> None:
        if params.width < 0 or params.width > self.config.max_width_us:
            raise ValueError(f"width out of range: {params.width}")
        if params.offset < 0 or params.offset > self.config.max_offset_us:
            raise ValueError(f"offset out of range: {params.offset}")
        if params.repeat <= 0 or params.repeat > self.config.max_repeat:
            raise ValueError(f"repeat out of range: {params.repeat}")

    def _wait_for_trigger(self) -> bool:
        assert self.config.trigger_in_pin is not None
        deadline = time.monotonic() + (self.config.trigger_timeout_ms / 1000.0)
        while time.monotonic() < deadline:
            if self.gpio.read(self.config.trigger_in_pin):
                return True
            self.gpio.sleep(0.0001)
        return False

    def _set_glitch(self, *, active: bool) -> None:
        self._set_pin(self.config.glitch_pin, active=active)

    def _set_pin(self, pin: int, *, active: bool) -> None:
        value = active if self.config.active_high else not active
        self.gpio.write(pin, value)

    def _idle_state(self) -> bool:
        return not self.config.active_high

    @staticmethod
    def _read_target_line(target_serial) -> bytes:
        if target_serial is None:
            return b""
        try:
            line = target_serial.read_until(b"\n")
        except Exception:
            return b""
        return bytes(line).strip()


def run_rpi_bridge(config: RPiBridgeConfig, *, gpio_backend: GPIOBackend | None = None) -> None:
    """Run serial protocol loop on Raspberry Pi."""
    try:
        import serial
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependent
        raise RuntimeError("pyserial is required to run rpi glitch bridge") from exc

    gpio = gpio_backend or RPiGPIOBackend()
    controller = RPiGlitchController(config=config, gpio_backend=gpio)

    control = serial.Serial(config.control_port, config.control_baudrate, timeout=config.control_timeout_s)
    target = (
        serial.Serial(config.target_uart_port, config.target_uart_baudrate, timeout=config.target_uart_timeout_s)
        if config.target_uart_port
        else None
    )

    try:
        buffer = b""
        while True:
            chunk = control.read(512)
            if not chunk:
                continue
            buffer += chunk

            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                line = raw.decode("utf-8", errors="replace").strip("\r")
                try:
                    response = controller.handle_line(line, target_serial=target)
                except Exception as exc:
                    response = f"err {type(exc).__name__}: {exc}".encode("utf-8", errors="replace")
                control.write(response.rstrip(b"\n") + b"\n")
    finally:
        try:
            controller.shutdown()
        finally:
            control.close()
            if target is not None:
                target.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AUTOGLITCH Raspberry Pi GPIO bridge")
    parser.add_argument("--control-port", required=True, help="control serial port (from host)")
    parser.add_argument("--control-baudrate", type=int, default=115200)
    parser.add_argument("--control-timeout-s", type=float, default=0.2)
    parser.add_argument("--glitch-pin", type=int, default=18, help="BCM pin for glitch pulse output")
    parser.add_argument("--reset-pin", type=int, default=23, help="BCM pin for reset pulse output")
    parser.add_argument("--trigger-out-pin", type=int, default=24, help="BCM pin for manual trigger output")
    parser.add_argument("--trigger-in-pin", type=int, default=None, help="BCM pin for trigger input")
    parser.add_argument("--active-high", action="store_true", help="use active-high pulse (default: active-low)")
    parser.add_argument("--reset-pulse-ms", type=float, default=20.0)
    parser.add_argument("--inter-pulse-gap-us", type=float, default=5.0)
    parser.add_argument("--wait-for-trigger", action="store_true")
    parser.add_argument("--trigger-timeout-ms", type=float, default=100.0)
    parser.add_argument("--max-width-us", type=float, default=5000.0)
    parser.add_argument("--max-offset-us", type=float, default=5_000_000.0)
    parser.add_argument("--max-repeat", type=int, default=128)
    parser.add_argument("--target-uart-port", default=None, help="optional target UART to echo line response")
    parser.add_argument("--target-uart-baudrate", type=int, default=115200)
    parser.add_argument("--target-uart-timeout-s", type=float, default=0.1)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    cfg = RPiBridgeConfig(
        control_port=args.control_port,
        control_baudrate=int(args.control_baudrate),
        control_timeout_s=float(args.control_timeout_s),
        glitch_pin=int(args.glitch_pin),
        reset_pin=int(args.reset_pin) if args.reset_pin is not None else None,
        trigger_out_pin=int(args.trigger_out_pin) if args.trigger_out_pin is not None else None,
        trigger_in_pin=int(args.trigger_in_pin) if args.trigger_in_pin is not None else None,
        active_high=bool(args.active_high),
        reset_pulse_ms=float(args.reset_pulse_ms),
        inter_pulse_gap_us=float(args.inter_pulse_gap_us),
        wait_for_trigger=bool(args.wait_for_trigger),
        trigger_timeout_ms=float(args.trigger_timeout_ms),
        max_width_us=float(args.max_width_us),
        max_offset_us=float(args.max_offset_us),
        max_repeat=int(args.max_repeat),
        target_uart_port=args.target_uart_port,
        target_uart_baudrate=int(args.target_uart_baudrate),
        target_uart_timeout_s=float(args.target_uart_timeout_s),
    )
    run_rpi_bridge(cfg)


if __name__ == "__main__":
    main()
