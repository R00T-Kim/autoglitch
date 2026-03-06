from __future__ import annotations

from dataclasses import dataclass, field

from src.tools.rpi_glitch_bridge import RPiBridgeConfig, RPiGlitchController
from src.types import GlitchParameters


@dataclass
class FakeGPIO:
    writes: list[tuple[int, bool]] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)
    inputs: dict[int, bool] = field(default_factory=dict)

    def setup_output(self, pin: int, initial: bool) -> None:
        self.writes.append((pin, initial))

    def setup_input(self, pin: int, pull_up: bool) -> None:
        self.inputs.setdefault(pin, False)

    def write(self, pin: int, value: bool) -> None:
        self.writes.append((pin, value))

    def read(self, pin: int) -> bool:
        return bool(self.inputs.get(pin, False))

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def cleanup(self) -> None:
        return None


def test_controller_reset_and_trigger_commands() -> None:
    cfg = RPiBridgeConfig(
        control_port="/dev/null",
        glitch_pin=18,
        reset_pin=23,
        trigger_out_pin=24,
        active_high=True,
    )
    gpio = FakeGPIO()
    controller = RPiGlitchController(config=cfg, gpio_backend=gpio)

    assert controller.handle_line("RESET") == b"reset ok"
    assert controller.handle_line("TRIGGER") == b"trigger ok"

    pins_written = [pin for pin, _ in gpio.writes]
    assert 23 in pins_written
    assert 24 in pins_written


def test_controller_glitch_command_sequence() -> None:
    cfg = RPiBridgeConfig(
        control_port="/dev/null",
        glitch_pin=18,
        reset_pin=None,
        trigger_out_pin=None,
        active_high=True,
        inter_pulse_gap_us=10.0,
    )
    gpio = FakeGPIO()
    controller = RPiGlitchController(config=cfg, gpio_backend=gpio)

    params = GlitchParameters(width=5.0, offset=20.0, repeat=2, ext_offset=0.0, voltage=0.0)
    controller.run_glitch(params)

    glitch_writes = [(pin, value) for pin, value in gpio.writes if pin == 18]
    # initialize idle + 2 pulses (high/low repeated)
    assert len(glitch_writes) >= 5
    assert any(value is True for _, value in glitch_writes)
    assert any(value is False for _, value in glitch_writes)


def test_controller_rejects_out_of_range() -> None:
    cfg = RPiBridgeConfig(control_port="/dev/null", max_repeat=4, max_width_us=100.0, max_offset_us=1000.0)
    gpio = FakeGPIO()
    controller = RPiGlitchController(config=cfg, gpio_backend=gpio)

    bad = GlitchParameters(width=101.0, offset=1.0, repeat=1, voltage=0.0, ext_offset=0.0)
    try:
        controller.run_glitch(bad)
    except ValueError as exc:
        assert "width out of range" in str(exc)
    else:
        raise AssertionError("expected ValueError")



def test_controller_handles_typed_hello() -> None:
    cfg = RPiBridgeConfig(control_port="/dev/null", glitch_pin=18)
    gpio = FakeGPIO()
    controller = RPiGlitchController(config=cfg, gpio_backend=gpio)

    response = controller.handle_line('{"command":"hello"}')
    assert b'autoglitch.v1' in response
