from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from src.cli_support import _load_config
from src.cli_validation import validate_hil_rc_command
from src.hardware.framework import HardwareBinding


def _args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    payload: dict[str, object] = {
        "config": "configs/default.yaml",
        "template": None,
        "target": "stm32f3",
        "config_mode": "strict",
        "hardware": None,
        "serial_port": "/dev/ttyUSB_FAKE",
        "serial_timeout": None,
        "serial_io": None,
        "binding_file": str(tmp_path / "hardware.yaml"),
        "plugin_dir": [],
        "run_tag": "hil_rc_unit",
        "output": str(tmp_path / "hil_rc_report.json"),
        "force_setup": True,
        "skip_software_gate": False,
        "warmup_trials": 5,
        "warmup_seed": 42,
        "stability_trials": 6,
        "stability_seeds": "101,202,303",
        "repro_trials": 4,
        "repro_seeds": "11,12,13,14,15",
        "preflight_probe_trials": 5,
        "preflight_max_timeout_rate": 0.03,
        "preflight_max_reset_rate": 0.08,
        "preflight_max_p95_latency_s": 0.40,
        "soak_duration_minutes": 0.01,
        "soak_batch_trials": 2,
        "soak_max_batches": 2,
        "skip_soak": False,
        "legacy_smoke_trials": 5,
        "skip_legacy_smoke": False,
        "manual_bridge_restart_ok": True,
        "manual_link_drop_ok": True,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def test_validate_hil_rc_command_emits_ready_report(monkeypatch, capsys, tmp_path: Path) -> None:
    config = _load_config(Path("configs/default.yaml"), "stm32f3")
    config.setdefault("hardware", {})["binding_file"] = str(tmp_path / "hardware.yaml")
    args = _args(tmp_path)

    monkeypatch.setattr(
        "src.cli_validation._run_software_gate",
        lambda: {"status": "passed", "ok": True, "passed": 108, "skipped": 3},
    )

    binding = HardwareBinding(
        adapter_id="serial-json-hardware",
        profile="serial-json-hardware",
        transport="serial",
        location="/dev/ttyUSB_FAKE",
        baudrate=115200,
        timeout_s=0.25,
        target="STM32F303",
    )
    monkeypatch.setattr(
        "src.cli_validation._run_primary_onboarding",
        lambda **kwargs: {
            "ok": True,
            "binding_file": str(tmp_path / "hardware.yaml"),
            "candidate_count": 1,
            "candidates": [],
            "selected_binding": binding.to_dict(),
            "selected_from": "auto-detect",
            "wrote_binding": True,
            "doctor": {"status": "ok", "findings": [], "healthcheck": {"ok": True}},
        },
    )
    monkeypatch.setattr(
        "src.cli_validation._run_primary_preflight",
        lambda **kwargs: {"valid": True, "report": str(tmp_path / "preflight.json")},
    )
    monkeypatch.setattr(
        "src.cli_validation._run_campaign_stage",
        lambda **kwargs: {
            "trials": kwargs["trials"],
            "seeds": list(kwargs["seeds"]),
            "runs": [
                {
                    "n_trials": kwargs["trials"],
                    "success_rate": 0.35,
                    "primitive_repro_rate": 0.25,
                    "latency_p95_seconds": 0.30,
                    "throughput_trials_per_second": 10.0,
                    "runtime_failure_ratio": 0.0,
                    "error_breakdown": {},
                }
                for _ in kwargs["seeds"]
            ],
            "aggregate": {
                "count": len(kwargs["seeds"]),
                "success_rate_mean": 0.35,
                "primitive_repro_rate_mean": 0.25,
                "latency_p95_max": 0.30,
                "throughput_mean": 10.0,
                "runtime_failure_ratio": 0.0,
            },
        },
    )
    monkeypatch.setattr("src.cli_validation._run_queue_guard_drill", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(
        "src.cli_validation._run_binding_lock_drill", lambda selected_binding: {"ok": True}
    )
    monkeypatch.setattr(
        "src.cli_validation._run_stale_binding_drill", lambda **kwargs: {"ok": True}
    )
    monkeypatch.setattr(
        "src.cli_validation._run_soak_resume_drill",
        lambda **kwargs: {
            "ok": True,
            "first": {"completed_batches": 1},
            "resume": {"completed_batches": 2},
        },
    )
    monkeypatch.setattr(
        "src.cli_validation._run_legacy_smoke",
        lambda **kwargs: {
            "ok": True,
            "preflight": {"valid": True},
            "run": {"report": "legacy.json"},
        },
    )

    validate_hil_rc_command(
        args,
        load_run_config=lambda supplied_args: (config, None),
        validate_runtime_config=lambda supplied_config, mode=None: [],
        execute_campaign=lambda supplied_args: {},
        run_hil_preflight_for_args=lambda *a, **k: {"valid": True},
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["gate_results"]["release_candidate_ready"] is True
    assert Path(payload["report"]).exists()


def test_validate_hil_rc_command_requires_manual_confirmation(monkeypatch, tmp_path: Path) -> None:
    config = _load_config(Path("configs/default.yaml"), "stm32f3")
    config.setdefault("hardware", {})["binding_file"] = str(tmp_path / "hardware.yaml")
    args = _args(tmp_path, manual_bridge_restart_ok=False, manual_link_drop_ok=False)

    monkeypatch.setattr(
        "src.cli_validation._run_software_gate",
        lambda: {"status": "passed", "ok": True, "passed": 108, "skipped": 3},
    )
    binding = HardwareBinding(
        adapter_id="serial-json-hardware",
        profile="serial-json-hardware",
        transport="serial",
        location="/dev/ttyUSB_FAKE",
    )
    monkeypatch.setattr(
        "src.cli_validation._run_primary_onboarding",
        lambda **kwargs: {
            "ok": True,
            "binding_file": str(tmp_path / "hardware.yaml"),
            "candidate_count": 1,
            "candidates": [],
            "selected_binding": binding.to_dict(),
            "selected_from": "auto-detect",
            "wrote_binding": True,
            "doctor": {"status": "ok", "findings": [], "healthcheck": {"ok": True}},
        },
    )
    monkeypatch.setattr(
        "src.cli_validation._run_primary_preflight", lambda **kwargs: {"valid": True}
    )
    monkeypatch.setattr(
        "src.cli_validation._run_campaign_stage",
        lambda **kwargs: {
            "trials": kwargs["trials"],
            "seeds": list(kwargs["seeds"]),
            "runs": [
                {
                    "n_trials": kwargs["trials"],
                    "success_rate": 0.4,
                    "primitive_repro_rate": 0.3,
                    "latency_p95_seconds": 0.2,
                    "throughput_trials_per_second": 10.0,
                    "runtime_failure_ratio": 0.0,
                    "error_breakdown": {},
                }
            ],
            "aggregate": {
                "count": 1,
                "success_rate_mean": 0.4,
                "primitive_repro_rate_mean": 0.3,
                "latency_p95_max": 0.2,
                "throughput_mean": 10.0,
                "runtime_failure_ratio": 0.0,
            },
        },
    )
    monkeypatch.setattr("src.cli_validation._run_queue_guard_drill", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(
        "src.cli_validation._run_binding_lock_drill", lambda selected_binding: {"ok": True}
    )
    monkeypatch.setattr(
        "src.cli_validation._run_stale_binding_drill", lambda **kwargs: {"ok": True}
    )
    monkeypatch.setattr("src.cli_validation._run_soak_resume_drill", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("src.cli_validation._run_legacy_smoke", lambda **kwargs: {"ok": True})

    with pytest.raises(SystemExit) as exc_info:
        validate_hil_rc_command(
            args,
            load_run_config=lambda supplied_args: (config, None),
            validate_runtime_config=lambda supplied_config, mode=None: [],
            execute_campaign=lambda supplied_args: {},
            run_hil_preflight_for_args=lambda *a, **k: {"valid": True},
        )

    assert exc_info.value.code == 2
