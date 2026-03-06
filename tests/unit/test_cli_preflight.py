from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import pytest

from src import cli
from src.cli import _execute_campaign, _hil_preflight_cmd, _load_config, _run_hil_preflight_for_args


def _run_args(**overrides) -> argparse.Namespace:
    payload = {
        "config": "configs/default.yaml",
        "template": None,
        "config_mode": "strict",
        "target": "stm32f3",
        "trials": 2,
        "optimizer": "bayesian",
        "bo_backend": "heuristic",
        "rl_backend": None,
        "enable_llm": False,
        "target_primitive": None,
        "hardware": "mock",
        "serial_port": None,
        "serial_timeout": None,
        "binding_file": None,
        "serial_io": None,
        "require_preflight": False,
        "rerun_count": 1,
        "fixed_seed": 123,
        "success_threshold": 0.3,
        "plugin_dir": [],
        "probe_trials": None,
        "max_timeout_rate": None,
        "max_reset_rate": None,
        "max_p95_latency_s": None,
        "output": None,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def test_execute_campaign_blocks_when_required_preflight_fails(monkeypatch) -> None:
    args = _run_args(require_preflight=True)

    monkeypatch.setattr(
        cli,
        "_run_hil_preflight_for_args",
        lambda *a, **k: {"valid": False, "report": "experiments/results/hil_preflight_fail.json"},
    )

    with pytest.raises(SystemExit) as exc_info:
        _execute_campaign(args)

    assert "HIL preflight failed" in str(exc_info.value)


def test_hil_preflight_command_skips_on_non_serial_hardware(capsys) -> None:
    args = _run_args(hardware="mock")
    _hil_preflight_cmd(args)
    out = json.loads(capsys.readouterr().out)

    assert out["skipped"] is True
    assert out["reason"] == "non_serial_hardware"


def test_run_hil_preflight_with_serial_mock_bridge(tmp_path) -> None:
    import threading
    import time

    from src.tools.mock_glitch_bridge import MockGlitchBridge

    bridge = MockGlitchBridge(seed=42)
    try:
        bridge.open_pty()
    except OSError as exc:
        pytest.skip(f"PTY unavailable in environment: {exc}")

    stop_event = threading.Event()
    thread = threading.Thread(target=bridge.serve_forever, kwargs={"stop_event": stop_event}, daemon=True)
    thread.start()

    try:
        time.sleep(0.05)
        config = _load_config(Path("configs/default.yaml"), "stm32f3")
        config = copy.deepcopy(config)
        config.setdefault("hardware", {})["mode"] = "serial"

        args = _run_args(
            hardware="serial",
            serial_port=bridge.port,
            serial_timeout=0.5,
            serial_io="sync",
            probe_trials=5,
            max_timeout_rate=0.5,
            max_reset_rate=0.5,
            max_p95_latency_s=1.0,
            output=str(tmp_path / "hil_preflight.json"),
        )

        result = _run_hil_preflight_for_args(args, config=config, force=True)
        assert result is not None
        assert "report" in result
        assert Path(result["report"]).exists()
    finally:
        stop_event.set()
        thread.join(timeout=1.0)
        bridge.close()
