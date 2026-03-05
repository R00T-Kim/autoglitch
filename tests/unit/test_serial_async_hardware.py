from __future__ import annotations

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
    reader = FakeAsyncReader([b"AUTH BYPASS success\n"])
    writer = FakeAsyncWriter()

    async def _factory(*_args, **_kwargs):
        return reader, writer

    hw = AsyncSerialCommandHardware(
        port="/dev/ttyUSB_FAKE",
        connection_factory=_factory,
    )

    result = hw.execute(GlitchParameters(width=8.0, offset=4.0, voltage=-0.1, repeat=2))

    assert result.serial_output == b"AUTH BYPASS success"
    assert result.error_code is None
    assert result.reset_detected is False
    assert writer.writes, "expected at least one command write"
    assert writer.closed is True


def test_async_serial_hardware_marks_error_and_reset() -> None:
    reader = FakeAsyncReader([b"panic: reset fault\n"])
    writer = FakeAsyncWriter()

    async def _factory(*_args, **_kwargs):
        return reader, writer

    hw = AsyncSerialCommandHardware(
        port="/dev/ttyUSB_FAKE",
        connection_factory=_factory,
    )

    result = hw.execute(GlitchParameters(width=1.0, offset=1.0, repeat=1, voltage=0.0))
    assert result.reset_detected is True
    assert result.error_code == 1
