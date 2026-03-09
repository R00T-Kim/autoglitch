from __future__ import annotations

import threading
import time

import pytest

from src.hardware import SerialCommandHardware, TypedSerialCommandHardware
from src.tools.mock_glitch_bridge import MockGlitchBridge
from src.types import GlitchParameters


def test_serial_command_hardware_with_mock_bridge() -> None:
    bridge = MockGlitchBridge(seed=42)
    try:
        bridge.open_pty()
    except OSError as exc:
        pytest.skip(f"PTY unavailable in environment: {exc}")

    stop_event = threading.Event()
    thread = threading.Thread(
        target=bridge.serve_forever,
        kwargs={"stop_event": stop_event},
        daemon=True,
    )
    thread.start()

    try:
        time.sleep(0.05)
        hardware = SerialCommandHardware(port=bridge.port, baudrate=115200, timeout=0.5)
        params = GlitchParameters(width=20.0, offset=10.0, voltage=-0.1, repeat=2, ext_offset=0.0)
        result = hardware.execute(params)
        hardware.disconnect()

        assert result.response_time >= 0.0
        assert isinstance(result.serial_output, bytes)
        assert len(result.serial_output) > 0
    finally:
        stop_event.set()
        thread.join(timeout=1.0)
        bridge.close()


def test_typed_serial_hardware_with_mock_bridge() -> None:
    bridge = MockGlitchBridge(seed=42)
    try:
        bridge.open_pty()
    except OSError as exc:
        pytest.skip(f"PTY unavailable in environment: {exc}")

    stop_event = threading.Event()
    thread = threading.Thread(
        target=bridge.serve_forever,
        kwargs={"stop_event": stop_event},
        daemon=True,
    )
    thread.start()

    try:
        time.sleep(0.05)
        hardware = TypedSerialCommandHardware(port=bridge.port, baudrate=115200, timeout=0.5)
        params = GlitchParameters(width=20.0, offset=10.0, voltage=-0.1, repeat=2, ext_offset=0.0)
        result = hardware.execute(params)
        hardware.disconnect()

        assert result.response_time >= 0.0
        assert isinstance(result.serial_output, bytes)
        assert len(result.serial_output) > 0
    finally:
        stop_event.set()
        thread.join(timeout=1.0)
        bridge.close()
