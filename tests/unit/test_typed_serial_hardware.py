from __future__ import annotations

import json

from src.hardware.typed_serial_hardware import TypedSerialCommandHardware
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


def test_typed_serial_hardware_executes_and_parses_result() -> None:
    fake = FakeSerial(
        [
            json.dumps(
                {
                    "status": "ok",
                    "serial_output": "AUTH BYPASS success",
                    "reset_detected": False,
                    "error_code": None,
                }
            ).encode()
            + b"\n",
            json.dumps({"status": "ok", "capabilities": ["glitch.execute", "healthcheck"]}).encode()
            + b"\n",
        ]
    )
    hardware = TypedSerialCommandHardware(
        port="/dev/ttyUSB_FAKE",
        serial_factory=lambda *args, **kwargs: fake,  # noqa: ARG005
    )

    result = hardware.execute(GlitchParameters(width=9.0, offset=2.0, voltage=-0.1, repeat=2))
    capabilities = hardware.get_capabilities()

    assert result.serial_output == b"AUTH BYPASS success"
    assert result.reset_detected is False
    assert result.error_code is None
    assert capabilities == ["glitch.execute", "healthcheck"]
    assert any(b'"command":"execute"' in payload for payload in fake.writes)

    hardware.disconnect()
    assert fake.closed is True


def test_typed_serial_probe_recognizes_autoglitch_v1() -> None:
    fake = FakeSerial(
        [
            json.dumps(
                {
                    "status": "ok",
                    "protocol": "autoglitch.v1",
                    "adapter_id": "serial-json-hardware",
                    "capabilities": ["glitch.execute"],
                    "identity": {"model": "mock-bridge"},
                }
            ).encode()
            + b"\n"
        ]
    )

    probe = TypedSerialCommandHardware.probe(
        port="/dev/ttyUSB_FAKE",
        baudrate=115200,
        timeout=0.25,
        serial_factory=lambda *args, **kwargs: fake,  # noqa: ARG005
    )

    assert probe is not None
    assert probe["reason"] == "typed_protocol_handshake_ok"
    assert probe["protocol"] == "autoglitch.v1"
