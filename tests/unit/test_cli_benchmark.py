from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli_commands import run_benchmark_command


def _benchmark_args() -> argparse.Namespace:
    return argparse.Namespace(
        config="configs/default.yaml",
        template=None,
        target="stm32f3",
        algorithms="bayesian,rl",
        backends="mock,chipwhisperer-hardware",
        runs=2,
        trials=5,
        bo_backend="heuristic",
        objective="single",
        hardware=None,
        serial_port=None,
        serial_timeout=None,
        serial_io=None,
        binding_file=None,
        rl_backend="lite",
        ai_mode="off",
        policy_file=None,
        require_preflight=False,
        config_mode="strict",
        success_threshold=0.30,
        run_tag="bench_unit",
        plugin_dir=[],
        benchmark_id="bench_unit",
        benchmark_task="det_fault",
        operator="alice",
        board_id="board-1",
        session_id="2026-03-09",
        wiring_profile="wire-a",
        board_prep_profile="prep-a",
        power_profile="psu-a",
    )


def test_run_benchmark_command_emits_backend_algorithm_matrix(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    report_paths: list[Path] = []

    def _fake_write_json_report(prefix: str, payload: dict) -> Path:
        path = tmp_path / f"{prefix}_{len(report_paths)}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        report_paths.append(path)
        return path

    def _fake_run_single_campaign(**kwargs) -> dict:
        args = kwargs["args"]
        backend = str(args.hardware)
        optimizer = str(args.optimizer)
        primitive_rate = (
            0.7 if backend == "chipwhisperer-hardware" and optimizer == "bayesian" else 0.4
        )
        return {
            "run_id": kwargs["run_id"],
            "seed": kwargs["run_seed"],
            "n_trials": kwargs["trials"],
            "success_rate": primitive_rate / 2,
            "primitive_repro_rate": primitive_rate,
            "time_to_first_valid_fault": 2,
            "time_to_first_primitive": 3,
            "runtime_total_seconds": 1.5,
            "execution_status_breakdown": {"ok": kwargs["trials"] - 1, "infra_failure": 1},
            "infra_failure_count": 1,
            "blocked_count": 0,
            "fault_distribution": {"AUTH_BYPASS": 2},
            "primitive_distribution": {"CODE_EXECUTION": 2},
            "artifact_bundle_status": {
                "required_ok": True,
                "research_complete": False,
                "rc_complete": False,
            },
        }

    monkeypatch.setattr("src.cli_commands._write_json_report", _fake_write_json_report)

    run_benchmark_command(_benchmark_args(), run_single_campaign=_fake_run_single_campaign)

    payload = json.loads(capsys.readouterr().out)
    assert payload["benchmark_id"] == "bench_unit"
    assert set(payload["backends"]) == {"mock-hardware", "chipwhisperer-hardware"}
    assert set(payload["results"]["chipwhisperer-hardware"].keys()) == {"bayesian", "rl"}
    assert payload["overall_winner"]["backend"] == "chipwhisperer-hardware"
    assert payload["overall_winner"]["algorithm"] == "bayesian"
    assert Path(payload["benchmark_report"]).exists()
    assert Path(payload["comparison_report"]).exists()
