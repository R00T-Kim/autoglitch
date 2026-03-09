from __future__ import annotations

import json
from pathlib import Path

import yaml

from src import cli


def _binding_args(tmp_path: Path, command: str) -> list[str]:
    return [
        command,
        "--config",
        "configs/default.yaml",
        "--target",
        "stm32f3",
        "--binding-file",
        str(tmp_path / "hardware.yaml"),
    ]


def test_detect_hardware_command_prints_candidates(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(
            lambda cls, *, port, baudrate, timeout, serial_factory=None: {  # noqa: ARG005
                "confidence": 0.99,
                "reason": "typed_protocol_handshake_ok",
                "identity": {"port": port},
            }
        ),
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )

    import sys

    argv = sys.argv
    sys.argv = [
        "autoglitch",
        *_binding_args(tmp_path, "detect-hardware"),
        "--serial-port",
        "/dev/ttyUSB_FAKE",
    ]
    try:
        cli.main()
    finally:
        sys.argv = argv

    payload = json.loads(capsys.readouterr().out)
    assert payload["detected"] >= 1
    assert any(
        item["adapter_id"] == "serial-json-hardware"
        and item["binding"]["location"] == "/dev/ttyUSB_FAKE"
        for item in payload["candidates"]
    )


def test_setup_hardware_command_writes_binding(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(
            lambda cls, *, port, baudrate, timeout, serial_factory=None: {  # noqa: ARG005
                "confidence": 0.99,
                "reason": "typed_protocol_handshake_ok",
                "identity": {"port": port},
            }
        ),
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )

    import sys

    argv = sys.argv
    binding_file = tmp_path / "hardware.yaml"
    sys.argv = [
        "autoglitch",
        *_binding_args(tmp_path, "setup-hardware"),
        "--serial-port",
        "/dev/ttyUSB_FAKE",
        "--force",
    ]
    try:
        cli.main()
    finally:
        sys.argv = argv

    payload = json.loads(capsys.readouterr().out)
    assert payload["binding"]["adapter_id"] == "serial-json-hardware"
    saved = yaml.safe_load(binding_file.read_text(encoding="utf-8"))
    assert saved["binding"]["location"] == "/dev/ttyUSB_FAKE"


def test_doctor_hardware_exits_nonzero_when_not_detected(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )

    import sys

    argv = sys.argv
    sys.argv = [
        "autoglitch",
        *_binding_args(tmp_path, "doctor-hardware"),
        "--serial-port",
        "/dev/ttyUSB_FAKE",
    ]
    try:
        try:
            cli.main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("expected SystemExit")
    finally:
        sys.argv = argv

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "degraded"
