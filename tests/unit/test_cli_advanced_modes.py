from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src import cli
from src.cli import _build_run_namespace, _execute_campaign, _queue_run, _soak_run


def _base_options() -> dict:
    return {
        "config": "configs/default.yaml",
        "template": None,
        "target": "stm32f3",
        "trials": 2,
        "optimizer": "bayesian",
        "bo_backend": "heuristic",
        "objective": "single",
        "enable_llm": False,
        "target_primitive": None,
        "hardware": "mock",
        "serial_port": None,
        "serial_timeout": None,
        "require_preflight": False,
        "rerun_count": 1,
        "fixed_seed": 123,
        "success_threshold": 0.3,
        "run_tag": "unit",
        "plugin_dir": [],
    }


def test_build_run_namespace_merges_plugin_dirs() -> None:
    ns = _build_run_namespace(
        {
            **_base_options(),
            "plugin_dir": ["/tmp/a", "/tmp/b"],
        },
        cli_plugin_dirs=["/tmp/c"],
    )

    assert ns.plugin_dir == ["/tmp/c", "/tmp/a", "/tmp/b"]
    assert ns.require_preflight is False
    assert ns.objective == "single"
    assert ns.run_tag == "unit"


def test_execute_campaign_returns_manifest_and_report() -> None:
    args = argparse.Namespace(**_base_options())
    output = _execute_campaign(args)

    run = output["runs"][0]
    assert run["n_trials"] == 2
    assert run["run_tag"] == "unit"
    assert Path(run["report"]).exists()
    assert Path(run["manifest"]).exists()


def test_queue_run_respects_priority_and_writes_checkpoint(tmp_path, monkeypatch, capsys) -> None:
    queue_file = tmp_path / "queue.yaml"
    queue_file.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "defaults:",
                "  config: configs/default.yaml",
                "  target: stm32f3",
                "  trials: 1",
                "jobs:",
                "  - name: low",
                "    priority: 1",
                "  - name: high",
                "    priority: 10",
                "  - name: mid",
                "    priority: 5",
            ]
        ),
        encoding="utf-8",
    )

    executed: list[str] = []

    def _fake_execute_campaign(args: argparse.Namespace) -> dict:
        executed.append(args.target)
        return {"ok": True, "target": args.target}

    monkeypatch.setattr(cli, "_execute_campaign", _fake_execute_campaign)
    monkeypatch.setattr(cli, "_write_json_report", lambda prefix, payload: tmp_path / f"{prefix}.json")

    args = argparse.Namespace(
        queue=str(queue_file),
        plugin_dir=[],
        checkpoint_file=str(tmp_path / "checkpoint.json"),
        resume=False,
        continue_on_error=False,
        respect_order=False,
        max_workers=1,
        job_interval_s=0.0,
        allow_parallel_serial=False,
    )

    _queue_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["completed_jobs"] == 3
    assert out["failed_jobs"] == 0
    assert out["jobs"][0]["job_name"] == "high"
    assert out["jobs"][1]["job_name"] == "mid"
    assert out["jobs"][2]["job_name"] == "low"
    assert Path(out["checkpoint_file"]).exists()
    assert len(executed) == 3


def test_queue_run_resume_skips_completed_jobs(tmp_path, monkeypatch, capsys) -> None:
    queue_file = tmp_path / "queue.yaml"
    queue_file.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "defaults:",
                "  config: configs/default.yaml",
                "  target: stm32f3",
                "  trials: 1",
                "jobs:",
                "  - name: first",
                "    priority: 10",
                "  - name: second",
                "    priority: 1",
            ]
        ),
        encoding="utf-8",
    )

    checkpoint_file = tmp_path / "checkpoint.json"
    digest = hashlib.sha256(queue_file.read_bytes()).hexdigest()
    checkpoint_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "queue": str(queue_file.resolve()),
                "queue_digest": digest,
                "created_at": "2026-03-05T00:00:00",
                "updated_at": "2026-03-05T00:00:00",
                "completed_job_keys": ["1:first", "2:second"],
                "jobs": {},
            }
        ),
        encoding="utf-8",
    )

    def _should_not_run(_args: argparse.Namespace) -> dict:
        raise AssertionError("resume mode should skip completed jobs")

    monkeypatch.setattr(cli, "_execute_campaign", _should_not_run)
    monkeypatch.setattr(cli, "_write_json_report", lambda prefix, payload: tmp_path / f"{prefix}.json")

    args = argparse.Namespace(
        queue=str(queue_file),
        plugin_dir=[],
        checkpoint_file=str(checkpoint_file),
        resume=True,
        continue_on_error=False,
        respect_order=False,
        max_workers=1,
        job_interval_s=0.0,
        allow_parallel_serial=False,
    )

    _queue_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["completed_jobs"] == 0
    assert out["skipped_jobs"] == 2
    assert all(item["status"] == "skipped_resume" for item in out["jobs"])


def _soak_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    payload = {
        "config": "configs/default.yaml",
        "template": None,
        "target": "stm32f3",
        "optimizer": "bayesian",
        "bo_backend": "heuristic",
        "enable_llm": False,
        "target_primitive": None,
        "hardware": "mock",
        "serial_port": None,
        "serial_timeout": None,
        "require_preflight": False,
        "fixed_seed": 100,
        "success_threshold": 0.3,
        "plugin_dir": [],
        "batch_trials": 2,
        "duration_minutes": 0.0,
        "max_batches": 2,
        "checkpoint_file": str(tmp_path / "soak_checkpoint.json"),
        "resume": False,
        "continue_on_error": False,
        "max_workers": 1,
        "batch_interval_s": 0.0,
        "allow_parallel_serial": False,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def test_soak_run_resume_skips_executed_batches(tmp_path, monkeypatch, capsys) -> None:
    call_count = {"value": 0}

    def _fake_execute_campaign(_args: argparse.Namespace) -> dict:
        call_count["value"] += 1
        return {
            "runs": [
                {
                    "run_id": f"run_{call_count['value']}",
                    "seed": 100 + call_count["value"],
                    "campaign_id": "campaign_1",
                    "n_trials": 2,
                    "success_rate": 0.5,
                    "primitive_repro_rate": 0.5,
                    "time_to_first_primitive": 1,
                    "optimizer_backend": "bayesian",
                    "circuit_breaker": {"state": "closed"},
                    "report": "r.json",
                    "manifest": "m.json",
                    "log": "l.jsonl",
                }
            ]
        }

    monkeypatch.setattr(cli, "_execute_campaign", _fake_execute_campaign)
    monkeypatch.setattr(cli, "_write_json_report", lambda prefix, payload: tmp_path / f"{prefix}.json")

    first_args = _soak_args(tmp_path, resume=False)
    _soak_run(first_args)
    first_out = json.loads(capsys.readouterr().out)
    assert first_out["new_batches"] == 2
    assert first_out["completed_batches"] == 2

    second_args = _soak_args(tmp_path, resume=True)
    _soak_run(second_args)
    second_out = json.loads(capsys.readouterr().out)
    assert second_out["new_batches"] == 0
    assert second_out["completed_batches"] == 2


def test_soak_run_continue_on_error_records_failed_batch(tmp_path, monkeypatch, capsys) -> None:
    call_count = {"value": 0}

    def _maybe_fail(_args: argparse.Namespace) -> dict:
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise SystemExit("first batch failed")
        return {
            "runs": [
                {
                    "run_id": "run_ok",
                    "seed": 101,
                    "campaign_id": "campaign_1",
                    "n_trials": 2,
                    "success_rate": 0.4,
                    "primitive_repro_rate": 0.2,
                    "time_to_first_primitive": 2,
                    "optimizer_backend": "bayesian",
                    "circuit_breaker": {"state": "closed"},
                    "report": "r.json",
                    "manifest": "m.json",
                    "log": "l.jsonl",
                }
            ]
        }

    monkeypatch.setattr(cli, "_execute_campaign", _maybe_fail)
    monkeypatch.setattr(cli, "_write_json_report", lambda prefix, payload: tmp_path / f"{prefix}.json")

    args = _soak_args(tmp_path, continue_on_error=True)
    _soak_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["new_batches"] == 2
    assert out["failed_batches"] == 1
    assert out["completed_batches"] == 1


def test_queue_run_parallel_workers(tmp_path, monkeypatch, capsys) -> None:
    queue_file = tmp_path / "queue_parallel.yaml"
    queue_file.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "defaults:",
                "  config: configs/default.yaml",
                "  target: stm32f3",
                "  trials: 1",
                "jobs:",
                "  - name: one",
                "    priority: 30",
                "  - name: two",
                "    priority: 20",
                "  - name: three",
                "    priority: 10",
            ]
        ),
        encoding="utf-8",
    )

    def _fake_execute_campaign(args: argparse.Namespace) -> dict:
        return {"ok": True, "target": args.target}

    monkeypatch.setattr(cli, "_execute_campaign", _fake_execute_campaign)
    monkeypatch.setattr(cli, "_write_json_report", lambda prefix, payload: tmp_path / f"{prefix}.json")

    args = argparse.Namespace(
        queue=str(queue_file),
        plugin_dir=[],
        checkpoint_file=str(tmp_path / "queue_checkpoint.json"),
        resume=False,
        continue_on_error=True,
        respect_order=False,
        max_workers=2,
        job_interval_s=0.0,
        allow_parallel_serial=False,
    )

    _queue_run(args)
    out = json.loads(capsys.readouterr().out)
    assert out["completed_jobs"] == 3
    assert out["failed_jobs"] == 0


def test_queue_run_parallel_requires_continue_on_error(tmp_path) -> None:
    queue_file = tmp_path / "queue_parallel_guard.yaml"
    queue_file.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "defaults:",
                "  config: configs/default.yaml",
                "jobs:",
                "  - name: one",
            ]
        ),
        encoding="utf-8",
    )

    args = argparse.Namespace(
        queue=str(queue_file),
        plugin_dir=[],
        checkpoint_file=str(tmp_path / "checkpoint.json"),
        resume=False,
        continue_on_error=False,
        respect_order=False,
        max_workers=2,
        job_interval_s=0.0,
        allow_parallel_serial=False,
    )

    try:
        _queue_run(args)
    except SystemExit as exc:
        assert "requires --continue-on-error" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_soak_run_parallel_workers(tmp_path, monkeypatch, capsys) -> None:
    def _fake_execute_campaign(_args: argparse.Namespace) -> dict:
        return {
            "runs": [
                {
                    "run_id": "run_ok",
                    "seed": 200,
                    "campaign_id": "campaign_1",
                    "n_trials": 2,
                    "success_rate": 0.5,
                    "primitive_repro_rate": 0.5,
                    "time_to_first_primitive": 1,
                    "optimizer_backend": "bayesian",
                    "circuit_breaker": {"state": "closed"},
                    "report": "r.json",
                    "manifest": "m.json",
                    "log": "l.jsonl",
                }
            ]
        }

    monkeypatch.setattr(cli, "_execute_campaign", _fake_execute_campaign)
    monkeypatch.setattr(cli, "_write_json_report", lambda prefix, payload: tmp_path / f"{prefix}.json")

    args = _soak_args(tmp_path, max_workers=2, continue_on_error=True, max_batches=4)
    _soak_run(args)
    out = json.loads(capsys.readouterr().out)

    assert out["new_batches"] == 4
    assert out["completed_batches"] == 4
    assert out["failed_batches"] == 0


def test_soak_run_require_preflight_executes_once(tmp_path, monkeypatch, capsys) -> None:
    preflight_calls = {"count": 0}
    campaign_calls = {"count": 0}

    def _fake_preflight(*_args, **_kwargs):
        preflight_calls["count"] += 1
        return {"valid": True, "report": str(tmp_path / "hil_preflight.json")}

    def _fake_execute_campaign(args: argparse.Namespace) -> dict:
        campaign_calls["count"] += 1
        assert args.require_preflight is False
        return {
            "runs": [
                {
                    "run_id": "run_ok",
                    "seed": 200,
                    "campaign_id": "campaign_1",
                    "n_trials": 2,
                    "success_rate": 0.5,
                    "primitive_repro_rate": 0.5,
                    "time_to_first_primitive": 1,
                    "optimizer_backend": "bayesian",
                    "circuit_breaker": {"state": "closed"},
                    "report": "r.json",
                    "manifest": "m.json",
                    "log": "l.jsonl",
                }
            ]
        }

    monkeypatch.setattr(cli, "_run_hil_preflight_for_args", _fake_preflight)
    monkeypatch.setattr(cli, "_load_run_config", lambda _args: ({}, None))
    monkeypatch.setattr(cli, "_validate_runtime_config", lambda _cfg, mode="strict": [])
    monkeypatch.setattr(cli, "_execute_campaign", _fake_execute_campaign)
    monkeypatch.setattr(cli, "_write_json_report", lambda prefix, payload: tmp_path / f"{prefix}.json")

    args = _soak_args(tmp_path, require_preflight=True, max_batches=2)
    _soak_run(args)
    out = json.loads(capsys.readouterr().out)

    assert preflight_calls["count"] == 1
    assert campaign_calls["count"] == 2
    assert out["preflight"]["valid"] is True
