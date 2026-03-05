from __future__ import annotations

from src.tools.mock_glitch_bridge import MockGlitchBridge, parse_glitch_params


def test_parse_glitch_params_basic() -> None:
    params = parse_glitch_params("GLITCH width=10.5 offset=2.0 voltage=-0.2 repeat=3 ext_offset=0.5")
    assert params.width == 10.5
    assert params.offset == 2.0
    assert params.voltage == -0.2
    assert params.repeat == 3
    assert params.ext_offset == 0.5


def test_parse_glitch_params_defaults() -> None:
    params = parse_glitch_params("GLITCH width=1.0 offset=2.0")
    assert params.voltage == 0.0
    assert params.repeat == 1
    assert params.ext_offset == 0.0


def test_bridge_handle_reset_and_trigger() -> None:
    bridge = MockGlitchBridge(seed=123)
    try:
        assert bridge.handle_command("RESET") == b"reset ok"
        assert bridge.handle_command("TRIGGER") == b"trigger ok"
    finally:
        bridge.close()

