from __future__ import annotations

from dataclasses import dataclass, field

from src.hardware import ChipWhispererHardware, detect_hardware
from src.types import GlitchParameters


@dataclass
class _FakeGlitch:
    offset: float = 0.0
    width: float = 0.0
    repeat: int = 1
    ext_offset: float = 0.0
    output: str = "glitch_only"
    trigger_src: str = "manual"
    manual_trigger_count: int = 0

    def manual_trigger(self) -> None:
        self.manual_trigger_count += 1


@dataclass
class _FakeIO:
    glitch_lp: bool = False


@dataclass
class _FakeScope:
    name: str = "Husky"
    glitch: _FakeGlitch = field(default_factory=_FakeGlitch)
    io: _FakeIO = field(default_factory=_FakeIO)
    default_setup_called: int = 0
    vglitch_setup_called: int = 0
    arm_called: int = 0
    capture_called: int = 0

    def default_setup(self) -> None:
        self.default_setup_called += 1

    def vglitch_setup(self) -> None:
        self.vglitch_setup_called += 1

    def arm(self) -> None:
        self.arm_called += 1

    def capture(self, timeout: float | None = None) -> bool:  # noqa: ARG002
        self.capture_called += 1
        return False

    def dis(self) -> None:
        return None


class _FakeCW:
    def __init__(self) -> None:
        self.scope_instance = _FakeScope()

    def list_devices(self) -> list[dict[str, object]]:
        return [{"name": "Husky", "sn": "CW123", "idProduct": 4660}]

    def scope(self, **kwargs) -> _FakeScope:
        assert kwargs["sn"] == "CW123"
        return self.scope_instance


class _FakeSerial:
    in_waiting = 0

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ARG002
        self.closed = False

    def reset_input_buffer(self) -> None:
        return None

    def read(self, size: int) -> bytes:  # noqa: ARG002
        return b"target-ok"

    def close(self) -> None:
        self.closed = True


def test_chipwhisperer_probe_filters_requested_device() -> None:
    fake_cw = _FakeCW()

    results = ChipWhispererHardware.probe(
        scope_name="Husky",
        serial_number="CW123",
        cw_module=fake_cw,
    )

    assert len(results) == 1
    assert results[0]["sn"] == "CW123"


def test_chipwhisperer_execute_maps_glitch_parameters() -> None:
    fake_cw = _FakeCW()
    adapter = ChipWhispererHardware(
        scope_name="Husky",
        serial_number="CW123",
        target_serial_port="/dev/ttyUSB0",
        target_baudrate=115200,
        target_timeout=0.1,
        serial_factory=lambda port, baudrate, timeout: _FakeSerial(port, baudrate, timeout),  # noqa: ARG005
        cw_module=fake_cw,
    )

    result = adapter.execute(
        params=GlitchParameters(width=12.0, offset=4.0, voltage=0.0, repeat=3, ext_offset=9.0)
    )

    assert result.serial_output == b"target-ok"
    assert fake_cw.scope_instance.glitch.offset == 4.0
    assert fake_cw.scope_instance.glitch.width == 12.0
    assert fake_cw.scope_instance.glitch.repeat == 3
    assert fake_cw.scope_instance.glitch.ext_offset == 9.0
    assert fake_cw.scope_instance.glitch.manual_trigger_count == 1


def test_detect_hardware_returns_chipwhisperer_candidate(monkeypatch) -> None:
    config = {
        "target": {"name": "STM32F303"},
        "hardware": {
            "mode": "auto",
            "adapter": "chipwhisperer-hardware",
            "transport": "usb",
            "binding_file": "configs/local/hardware.yaml",
            "target": {"timeout": 1.0},
            "chipwhisperer": {"scope_name": "Husky", "serial_number": "CW123"},
            "discovery": {
                "enabled": True,
                "candidate_ports": [],
                "port_globs": [],
                "probe_timeout_s": 0.25,
            },
        },
    }

    monkeypatch.setattr(
        "src.hardware.chipwhisperer_hardware.ChipWhispererHardware.probe",
        classmethod(
            lambda cls, *, scope_name=None, serial_number=None, id_product=None, cw_module=None: [  # noqa: ARG005
                {"name": scope_name, "sn": serial_number, "idProduct": id_product, "raw": {}}
            ]
        ),
    )

    candidates = detect_hardware(config=config, explicit_adapter="chipwhisperer-hardware")

    assert len(candidates) == 1
    assert candidates[0].profile.adapter_id == "chipwhisperer-hardware"
    assert candidates[0].binding.location == "chipwhisperer://CW123"
