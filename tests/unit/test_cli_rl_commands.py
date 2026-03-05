from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli import _eval_rl_cmd, _train_rl_cmd


def _train_args(**overrides) -> argparse.Namespace:
    payload = {
        "config": "configs/default.yaml",
        "template": None,
        "target": "stm32f3",
        "config_mode": "strict",
        "rl_backend": "sb3",
        "steps": 24,
        "run_tag": "unit-train",
        "plugin_dir": [],
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def _eval_args(**overrides) -> argparse.Namespace:
    payload = {
        "config": "configs/default.yaml",
        "template": None,
        "target": "stm32f3",
        "config_mode": "strict",
        "rl_backend": "sb3",
        "episodes": 10,
        "checkpoint": None,
        "run_tag": "unit-eval",
        "plugin_dir": [],
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def test_train_rl_cmd_emits_report(capsys) -> None:
    args = _train_args(steps=12)
    _train_rl_cmd(args)
    payload = json.loads(capsys.readouterr().out)

    assert payload["result"]["steps_run"] >= 12
    assert Path(payload["report"]).exists()


def test_eval_rl_cmd_loads_checkpoint_when_available(capsys) -> None:
    train_args = _train_args(steps=20, run_tag="rl-checkpoint")
    _train_rl_cmd(train_args)
    train_payload = json.loads(capsys.readouterr().out)
    checkpoint = train_payload["result"].get("checkpoint")
    assert checkpoint is not None
    assert Path(checkpoint).exists()

    eval_args = _eval_args(checkpoint=checkpoint, run_tag="rl-checkpoint")
    _eval_rl_cmd(eval_args)
    eval_payload = json.loads(capsys.readouterr().out)

    assert eval_payload["checkpoint_loaded"] == checkpoint
    assert eval_payload["evaluation"]["episodes"] == 10
    assert Path(eval_payload["report"]).exists()
