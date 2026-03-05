from __future__ import annotations

from src.hardware.serial_hardware import SerialCommandHardware
from src.types import GlitchParameters


class FakeSerial:
    def __init__(self, responses: list[bytes]):
        self._responses = responses
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)

    def read_until(self, marker: bytes) -> bytes:  # noqa: ARG002
        if self._responses:
            return self._responses.pop(0)
        return b""

    def close(self) -> None:
        self.closed = True


def test_serial_hardware_executes_and_parses_success() -> None:
    fake = FakeSerial([b"AUTH BYPASS success\n"])

    hw = SerialCommandHardware(
        port="/dev/ttyUSB_FAKE",
        serial_factory=lambda *args, **kwargs: fake,  # noqa: ARG005
    )

    result = hw.execute(GlitchParameters(width=10.0, offset=5.0, voltage=-0.2, repeat=2))

    assert result.serial_output == b"AUTH BYPASS success"
    assert result.error_code is None
    assert result.reset_detected is False
    assert fake.writes, "expected serial command write"

    hw.disconnect()
    assert fake.closed is True


def test_serial_hardware_marks_error_and_reset_from_response() -> None:
    fake = FakeSerial([b"panic: reset fault\n"])
    hw = SerialCommandHardware(
        port="/dev/ttyUSB_FAKE",
        serial_factory=lambda *args, **kwargs: fake,  # noqa: ARG005
    )

    result = hw.execute(GlitchParameters(width=1.0, offset=1.0, repeat=1))

    assert result.reset_detected is True
    assert result.error_code == 1
