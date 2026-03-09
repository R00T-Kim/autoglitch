from __future__ import annotations

import argparse
from pathlib import Path

from src.cli import _load_config
from src.cli_runtime import _create_hardware
from src.hardware import ChipWhispererHardware, TypedSerialCommandHardware


def test_create_hardware_honors_profile_dirs_for_registry_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "serial-json-hardware.yaml").write_text(
        "\n".join(
            [
                "adapter_id: serial-json-hardware",
                "display_name: Custom Typed Serial",
                "transport: serial",
                "protocol: autoglitch.v1",
                "supported_targets:",
                "  - stm32f303",
                "default_baudrate: 57600",
                "default_timeout_s: 0.75",
            ]
        ),
        encoding="utf-8",
    )

    config = _load_config(Path("configs/default.yaml"), "stm32f3")
    config["hardware"]["profile_dirs"] = [str(profile_dir)]
    config["hardware"]["adapter"] = "serial-json-hardware"
    config["hardware"]["mode"] = "auto"
    config["hardware"]["target"] = {"type": "stm32f3"}
    config["hardware"]["discovery"] = {
        "enabled": True,
        "candidate_ports": ["/dev/ttyUSB_PROFILE"],
        "port_globs": [],
    }

    monkeypatch.setattr(
        "src.hardware.typed_serial_hardware.TypedSerialCommandHardware.probe",
        classmethod(
            lambda cls, *, port, baudrate, timeout, serial_factory=None: {  # noqa: ARG005
                "confidence": 0.99,
                "reason": "typed_protocol_handshake_ok",
                "identity": {"port": port, "baudrate": baudrate, "timeout": timeout},
            }
        ),
    )
    monkeypatch.setattr(
        "src.hardware.serial_hardware.SerialCommandHardware.probe",
        classmethod(lambda cls, *, port, baudrate, timeout, serial_factory=None: None),  # noqa: ARG005
    )

    args = argparse.Namespace(
        serial_timeout=None,
        serial_io=None,
        hardware=None,
        serial_port=None,
        binding_file=None,
    )
    hardware = _create_hardware(args=args, config=config, seed=7)

    assert isinstance(hardware, TypedSerialCommandHardware)
    assert hardware.baudrate == 57600
    assert hardware.timeout == 0.75


def test_create_hardware_routes_serial_port_to_chipwhisperer_target_uart(
    monkeypatch,
) -> None:
    config = _load_config(Path("configs/default.yaml"), "stm32f3")
    config["hardware"]["adapter"] = "chipwhisperer-hardware"
    config["hardware"]["transport"] = "usb"
    config["hardware"]["chipwhisperer"]["scope_name"] = "Husky"
    config["hardware"]["chipwhisperer"]["serial_number"] = "CW123"
    config["hardware"]["chipwhisperer"]["target_serial_port"] = None

    monkeypatch.setattr(
        "src.hardware.chipwhisperer_hardware.ChipWhispererHardware.probe",
        classmethod(
            lambda cls, *, scope_name=None, serial_number=None, id_product=None, cw_module=None: [  # noqa: ARG005
                {"name": scope_name, "sn": serial_number, "idProduct": id_product, "raw": {}}
            ]
        ),
    )

    args = argparse.Namespace(
        serial_timeout=None,
        serial_io=None,
        hardware="chipwhisperer-hardware",
        serial_port="/dev/ttyUSB_TARGET",
        binding_file=None,
    )
    hardware = _create_hardware(args=args, config=config, seed=7)

    assert isinstance(hardware, ChipWhispererHardware)
    assert hardware.target_serial_port == "/dev/ttyUSB_TARGET"
