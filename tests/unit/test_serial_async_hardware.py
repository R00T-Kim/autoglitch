from __future__ import annotations

import asyncio
from typing import Any

from src.hardware.serial_async_hardware import AsyncSerialCommandHardware
from src.types import GlitchParameters


class FakeAsyncReader:
    def __init__(self, responses: list[bytes]):
        self._responses = responses

    async def readline(self) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b""


class FakeAsyncWriter:
    def __init__(self):
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def test_async_serial_hardware_executes_and_parses_success() -> None:
    reader = FakeAsyncReader([b"AUTH BYPASS success\n", b"AUTH BYPASS success\n"])
    writer = FakeAsyncWriter()
    calls = {"count": 0}

    async def _factory(*_args, **_kwargs):
        calls["count"] += 1
        return reader, writer

    hw = AsyncSerialCommandHardware(
        port="/dev/ttyUSB_FAKE",
        connection_factory=_factory,
    )

    result = hw.execute(GlitchParameters(width=8.0, offset=4.0, voltage=-0.1, repeat=2))
    second = hw.execute(GlitchParameters(width=9.0, offset=5.0, voltage=-0.2, repeat=2))

    assert result.serial_output == b"AUTH BYPASS success"
    assert second.serial_output == b"AUTH BYPASS success"
    assert result.error_code is None
    assert result.reset_detected is False
    assert writer.writes, "expected at least one command write"
    assert calls["count"] == 1, "persistent async connection should be reused"
    assert writer.closed is False
    assert hw.connection_state == "connected"

    hw.disconnect()
    assert writer.closed is True
    assert hw.connection_state == "disconnected"


def test_async_serial_hardware_marks_error_and_reset() -> None:
    reader = FakeAsyncReader([b"panic: reset fault\n"])
    writer = FakeAsyncWriter()

    async def _factory(*_args, **_kwargs):
        return reader, writer

    hw = AsyncSerialCommandHardware(
        port="/dev/ttyUSB_FAKE",
        keep_open=False,
        connection_factory=_factory,
    )

    result = hw.execute(GlitchParameters(width=1.0, offset=1.0, repeat=1, voltage=0.0))
    assert result.reset_detected is True
    assert result.error_code == 1
    assert writer.closed is True


def test_async_serial_hardware_reconnects_after_connection_error() -> None:
    calls = {"count": 0}
    reader = FakeAsyncReader([b"ok\n"])
    writer = FakeAsyncWriter()

    async def _factory(*_args: Any, **_kwargs: Any):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient open error")
        return reader, writer

    hw = AsyncSerialCommandHardware(
        port="/dev/ttyUSB_FAKE",
        reconnect_attempts=1,
        reconnect_backoff_s=0.0,
        connection_factory=_factory,
    )

    result = hw.execute(GlitchParameters(width=3.0, offset=2.0, repeat=1, voltage=0.0))
    assert result.serial_output == b"ok"
    assert calls["count"] == 2


def test_async_serial_hardware_sync_methods_work_with_running_event_loop() -> None:
    reader = FakeAsyncReader([b"ok\n", b"ok-again\n"])
    writer = FakeAsyncWriter()
    calls = {"count": 0}

    async def _factory(*_args: Any, **_kwargs: Any):
        calls["count"] += 1
        return reader, writer

    hw = AsyncSerialCommandHardware(
        port="/dev/ttyUSB_FAKE",
        connection_factory=_factory,
    )

    async def _exercise() -> tuple[bytes, bytes]:
        hw.connect()
        first = hw.execute(GlitchParameters(width=4.0, offset=1.0, repeat=1, voltage=0.0))
        second = hw.execute(GlitchParameters(width=5.0, offset=2.0, repeat=1, voltage=0.0))
        hw.disconnect()
        return first.serial_output, second.serial_output

    first_output, second_output = asyncio.run(_exercise())

    assert first_output == b"ok"
    assert second_output == b"ok-again"
    assert calls["count"] == 1
    assert writer.closed is True
    assert hw.connection_state == "disconnected"
