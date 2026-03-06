from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli import _execute_campaign, _kb_ingest_cmd, _kb_query_cmd, _planner_step_cmd


def _run_args(template: str, **overrides) -> argparse.Namespace:
    payload = {
        "config": "configs/default.yaml",
        "template": template,
        "config_mode": "strict",
        "target": "stm32f3",
        "trials": 4,
        "optimizer": "bayesian",
        "bo_backend": "heuristic",
        "rl_backend": None,
        "ai_mode": "agentic_shadow",
        "policy_file": "configs/policy/default_policy.yaml",
        "objective": "multi",
        "enable_llm": False,
        "target_primitive": None,
        "hardware": "mock",
        "serial_port": None,
        "serial_timeout": None,
        "serial_io": None,
        "require_preflight": False,
        "rerun_count": 1,
        "fixed_seed": 123,
        "success_threshold": 0.3,
        "run_tag": "agentic-test",
        "plugin_dir": [],
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def test_execute_campaign_agentic_shadow_records_events(tmp_path) -> None:
    template = tmp_path / "agentic_template.yaml"
    template.write_text(
        "\n".join(
            [
                "name: agentic_unit",
                "base_config: configs/default.yaml",
                "target: stm32f3",
                "experiment:",
                "  max_trials: 4",
                "ai:",
                "  mode: agentic_shadow",
                "  planner_interval_trials: 1",
                "  confidence_threshold: 0.1",
                "policy:",
                "  max_patch_delta: 1.0",
                "  max_actions_per_cycle: 3",
            ]
        ),
        encoding="utf-8",
    )
    args = _run_args(template=str(template))
    output = _execute_campaign(args)

    run = output["runs"][0]
    assert run["ai_mode"] == "agentic_shadow"
    assert run["agentic"]["mode"] == "agentic_shadow"
    assert len(run["agentic"]["events"]) >= 1
    first_event = run["agentic"]["events"][0]
    assert first_event["verdict"]["validation_stage"] in {"policy", "confidence_gate"}
    assert isinstance(first_event["apply_status_by_path"], dict)
    assert Path(run["agentic"]["trace_report"]).suffix == ".jsonl"
    assert Path(run["agentic"]["trace_report"]).exists()


def test_planner_step_command_outputs_policy_verdict(capsys) -> None:
    args = argparse.Namespace(
        config="configs/default.yaml",
        template=None,
        target="stm32f3",
        config_mode="strict",
        ai_mode="agentic_enforced",
        policy_file="configs/policy/default_policy.yaml",
        trial_index=50,
        window_size=25,
        success_rate=0.1,
        primitive_rate=0.05,
        timeout_rate=0.01,
        reset_rate=0.01,
        latency_p95=0.2,
    )
    _planner_step_cmd(args)
    payload = json.loads(capsys.readouterr().out)

    assert payload["ai_mode"] == "agentic_enforced"
    assert "proposal" in payload
    assert "policy_verdict" in payload
    assert "validation_stage" in payload["policy_verdict"]
    assert "effect_type_by_path" in payload["policy_verdict"]
    assert "validation_status_by_path" in payload["policy_verdict"]


def test_kb_ingest_and_query_roundtrip(tmp_path, capsys) -> None:
    store = tmp_path / "kb.jsonl"
    ingest_args = argparse.Namespace(
        store=str(store),
        source_file=None,
        text="STM32 glitch timeout pattern and exploration strategy",
        title="note-1",
        tags="stm32,timeout",
    )
    _kb_ingest_cmd(ingest_args)
    ingest_payload = json.loads(capsys.readouterr().out)
    assert ingest_payload["store"] == str(store)

    query_args = argparse.Namespace(
        store=str(store),
        query="timeout strategy",
        top_k=3,
    )
    _kb_query_cmd(query_args)
    query_payload = json.loads(capsys.readouterr().out)
    assert query_payload["hits"]
    assert "timeout" in query_payload["hits"][0]["content"].lower()
