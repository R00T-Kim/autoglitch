"""Argument parser builders for the AUTOGLITCH CLI."""
from __future__ import annotations

import argparse


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AUTOGLITCH CLI")
    parser.add_argument("--log-level", default="INFO", help="logging level (default: INFO)")

    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="run glitch campaign")
    _add_run_arguments(run)

    queue = sub.add_parser("queue-run", help="run jobs from queue yaml")
    queue.add_argument("--queue", required=True, help="queue YAML path")
    queue.add_argument("--plugin-dir", action="append", default=[], help="extra plugin manifest directory")
    queue.add_argument("--config-mode", choices=["strict", "legacy"], default=None)
    queue.add_argument("--serial-io", choices=["sync", "async"], default=None)
    queue.add_argument("--rl-backend", choices=["lite", "sb3"], default=None)
    queue.add_argument("--ai-mode", choices=["off", "advisor", "agentic_shadow", "agentic_enforced"], default=None)
    queue.add_argument("--policy-file", default=None, help="agentic policy yaml path")
    queue.add_argument("--run-tag", default=None, help="optional run tag applied to queue jobs")
    queue.add_argument(
        "--require-preflight",
        action="store_true",
        help="require serial HIL preflight pass before each queue job",
    )
    queue.add_argument(
        "--checkpoint-file",
        default=None,
        help="optional checkpoint JSON path (default: experiments/results/queue_checkpoint_<name>.json)",
    )
    queue.add_argument("--resume", action="store_true", help="resume from checkpoint file")
    queue.add_argument(
        "--continue-on-error",
        action="store_true",
        help="continue executing remaining jobs when a job fails",
    )
    queue.add_argument(
        "--respect-order",
        action="store_true",
        help="execute jobs in YAML order (ignore priority field)",
    )
    queue.add_argument("--max-workers", type=int, default=1, help="parallel queue workers (default: 1)")
    queue.add_argument("--job-interval-s", type=float, default=0.0, help="delay between job dispatches")
    queue.add_argument(
        "--allow-parallel-serial",
        action="store_true",
        help="allow max-workers > 1 when job hardware is serial (unsafe by default)",
    )

    soak = sub.add_parser("soak", help="long-running soak campaign")
    _add_run_arguments(soak)
    soak.add_argument("--duration-minutes", type=float, default=60.0, help="soak duration in minutes")
    soak.add_argument("--batch-trials", type=int, default=200, help="trials per soak batch")
    soak.add_argument("--max-batches", type=int, default=None, help="optional hard cap for batches")
    soak.add_argument(
        "--checkpoint-file",
        default=None,
        help="optional checkpoint JSON path (default: experiments/results/soak_checkpoint_<name>.json)",
    )
    soak.add_argument("--resume", action="store_true", help="resume from soak checkpoint")
    soak.add_argument(
        "--continue-on-error",
        action="store_true",
        help="continue remaining soak batches even if one batch fails",
    )
    soak.add_argument("--max-workers", type=int, default=1, help="parallel soak batch workers (default: 1)")
    soak.add_argument("--batch-interval-s", type=float, default=0.0, help="delay between batch dispatches")
    soak.add_argument(
        "--allow-parallel-serial",
        action="store_true",
        help="allow max-workers > 1 when soak hardware is serial (unsafe by default)",
    )

    report = sub.add_parser("report", help="show campaign report")
    report.add_argument("--file", default=None, help="path to report json file")

    validate = sub.add_parser("validate-config", help="validate config + safety/recovery constraints")
    validate.add_argument("--config", default="configs/default.yaml", help="base config path")
    validate.add_argument("--template", default=None, help="campaign template yaml path")
    validate.add_argument("--target", default="stm32f3", help="target profile name")
    validate.add_argument(
        "--config-mode",
        choices=["strict", "legacy"],
        default="strict",
        help="config validation mode (default: strict)",
    )

    plugins = sub.add_parser("list-plugins", help="list plugin manifests")
    plugins.add_argument("--kind", default=None, help="filter by plugin kind")
    plugins.add_argument("--plugin-dir", action="append", default=[], help="extra plugin manifest directory")

    benchmark = sub.add_parser("benchmark", help="compare algorithms on the same campaign template")
    benchmark.add_argument("--config", default="configs/default.yaml", help="base config path")
    benchmark.add_argument("--template", default=None, help="campaign template yaml path")
    benchmark.add_argument("--target", default="stm32f3", help="target profile name")
    benchmark.add_argument("--algorithms", default="bayesian,rl", help="comma-separated algorithms")
    benchmark.add_argument("--runs", type=int, default=5, help="runs per algorithm")
    benchmark.add_argument("--trials", type=int, default=200, help="trials per run")
    benchmark.add_argument(
        "--bo-backend",
        choices=["auto", "heuristic", "botorch", "turbo", "qnehvi"],
        default="auto",
    )
    benchmark.add_argument("--objective", choices=["single", "multi"], default="single")
    benchmark.add_argument("--hardware", default=None, help="hardware adapter id or legacy mode override")
    benchmark.add_argument("--serial-port", default=None)
    benchmark.add_argument("--serial-timeout", type=float, default=None)
    benchmark.add_argument("--serial-io", choices=["sync", "async"], default=None)
    benchmark.add_argument("--binding-file", default=None)
    benchmark.add_argument("--rl-backend", choices=["lite", "sb3"], default=None)
    benchmark.add_argument("--ai-mode", choices=["off", "advisor", "agentic_shadow", "agentic_enforced"], default=None)
    benchmark.add_argument("--policy-file", default=None, help="agentic policy yaml path")
    benchmark.add_argument("--require-preflight", action="store_true")
    benchmark.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    benchmark.add_argument("--success-threshold", type=float, default=0.30)
    benchmark.add_argument("--run-tag", default=None)
    benchmark.add_argument("--plugin-dir", action="append", default=[])

    replay = sub.add_parser("replay", help="recompute summary from a trial JSONL log")
    replay.add_argument("--log", required=True, help="path to trial jsonl log")
    replay.add_argument("--report", default=None, help="optional report json to compare against")

    preflight = sub.add_parser("hil-preflight", help="run serial HIL preflight probe")
    preflight.add_argument("--config", default="configs/default.yaml", help="base config path")
    preflight.add_argument("--template", default=None, help="campaign template yaml path")
    preflight.add_argument("--target", default="stm32f3", help="target profile name")
    preflight.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    preflight.add_argument("--hardware", default=None, help="hardware adapter id or legacy mode override")
    preflight.add_argument("--serial-port", default=None)
    preflight.add_argument("--serial-timeout", type=float, default=None)
    preflight.add_argument("--serial-io", choices=["sync", "async"], default=None)
    preflight.add_argument("--binding-file", default=None)
    preflight.add_argument("--probe-trials", type=int, default=None)
    preflight.add_argument("--max-timeout-rate", type=float, default=None)
    preflight.add_argument("--max-reset-rate", type=float, default=None)
    preflight.add_argument("--max-p95-latency-s", type=float, default=None)
    preflight.add_argument("--output", default=None, help="optional preflight report output path")
    preflight.add_argument("--plugin-dir", action="append", default=[])

    train_rl = sub.add_parser("train-rl", help="train RL optimizer and emit checkpoint/report")
    train_rl.add_argument("--config", default="configs/default.yaml", help="base config path")
    train_rl.add_argument("--template", default=None, help="campaign template yaml path")
    train_rl.add_argument("--target", default="stm32f3", help="target profile name")
    train_rl.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    train_rl.add_argument("--rl-backend", choices=["lite", "sb3"], default="sb3")
    train_rl.add_argument("--steps", type=int, default=None, help="training steps override")
    train_rl.add_argument("--run-tag", default=None, help="optional run tag for report naming/metadata")
    train_rl.add_argument("--plugin-dir", action="append", default=[])

    eval_rl = sub.add_parser("eval-rl", help="evaluate RL checkpoint or current policy")
    eval_rl.add_argument("--config", default="configs/default.yaml", help="base config path")
    eval_rl.add_argument("--template", default=None, help="campaign template yaml path")
    eval_rl.add_argument("--target", default="stm32f3", help="target profile name")
    eval_rl.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    eval_rl.add_argument("--rl-backend", choices=["lite", "sb3"], default="sb3")
    eval_rl.add_argument("--episodes", type=int, default=50, help="evaluation episodes")
    eval_rl.add_argument("--checkpoint", default=None, help="optional checkpoint path to load")
    eval_rl.add_argument("--run-tag", default=None, help="optional run tag for report metadata")
    eval_rl.add_argument("--plugin-dir", action="append", default=[])

    run_agentic = sub.add_parser("run-agentic", help="run campaign with agentic planner/policy loop")
    _add_run_arguments(run_agentic)
    run_agentic.set_defaults(ai_mode="agentic_enforced")

    planner_step = sub.add_parser("planner-step", help="generate + validate one planner proposal")
    planner_step.add_argument("--config", default="configs/default.yaml", help="base config path")
    planner_step.add_argument("--template", default=None, help="campaign template yaml path")
    planner_step.add_argument("--target", default="stm32f3", help="target profile name")
    planner_step.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    planner_step.add_argument("--ai-mode", choices=["off", "advisor", "agentic_shadow", "agentic_enforced"], default=None)
    planner_step.add_argument("--policy-file", default=None, help="agentic policy yaml path")
    planner_step.add_argument("--trial-index", type=int, default=50)
    planner_step.add_argument("--window-size", type=int, default=50)
    planner_step.add_argument("--success-rate", type=float, default=0.05)
    planner_step.add_argument("--primitive-rate", type=float, default=0.01)
    planner_step.add_argument("--timeout-rate", type=float, default=0.02)
    planner_step.add_argument("--reset-rate", type=float, default=0.01)
    planner_step.add_argument("--latency-p95", type=float, default=0.2)

    eval_suite = sub.add_parser("eval-suite", help="run reproducibility suite for templates/targets")
    eval_suite.add_argument(
        "--templates",
        default="experiments/configs/repro_stm32f3.yaml,experiments/configs/repro_esp32.yaml",
    )
    eval_suite.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    eval_suite.add_argument("--ai-mode", choices=["off", "advisor", "agentic_shadow", "agentic_enforced"], default="off")
    eval_suite.add_argument("--policy-file", default=None, help="agentic policy yaml path")
    eval_suite.add_argument("--success-threshold", type=float, default=0.3)
    eval_suite.add_argument("--run-tag", default=None)

    kb_ingest = sub.add_parser("kb-ingest", help="ingest a note/file into local knowledge store")
    kb_ingest.add_argument("--store", default=None, help="override knowledge store jsonl path")
    kb_ingest.add_argument("--source-file", default=None, help="path to markdown/text file")
    kb_ingest.add_argument("--text", default=None, help="inline text content")
    kb_ingest.add_argument("--title", default=None, help="document title")
    kb_ingest.add_argument("--tags", default="", help="comma-separated tags")

    detect_hw = sub.add_parser("detect-hardware", help="probe supported hardware adapters on this machine")
    _add_hardware_management_arguments(detect_hw)

    setup_hw = sub.add_parser("setup-hardware", help="auto-detect and persist a local hardware binding")
    _add_hardware_management_arguments(setup_hw)
    setup_hw.add_argument("--force", action="store_true", help="overwrite existing local binding file")

    doctor_hw = sub.add_parser("doctor-hardware", help="diagnose hardware binding and detection health")
    _add_hardware_management_arguments(doctor_hw)

    kb_query = sub.add_parser("kb-query", help="query local knowledge store")
    kb_query.add_argument("--store", default=None, help="override knowledge store jsonl path")
    kb_query.add_argument("--query", required=True, help="search query")
    kb_query.add_argument("--top-k", type=int, default=None, help="override retrieval top-k")

    return parser


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="configs/default.yaml", help="base config path")
    parser.add_argument("--template", default=None, help="campaign template yaml path")
    parser.add_argument(
        "--config-mode",
        choices=["strict", "legacy"],
        default="strict",
        help="config validation mode (default: strict)",
    )
    parser.add_argument("--target", default="stm32f3", help="target profile name (stm32f3, esp32)")
    parser.add_argument("--trials", type=int, default=None, help="number of campaign trials")
    parser.add_argument("--optimizer", choices=["bayesian", "rl"], default=None)
    parser.add_argument("--bo-backend", choices=["auto", "heuristic", "botorch", "turbo", "qnehvi"], default=None)
    parser.add_argument("--rl-backend", choices=["lite", "sb3"], default=None)
    parser.add_argument("--ai-mode", choices=["off", "advisor", "agentic_shadow", "agentic_enforced"], default=None)
    parser.add_argument("--policy-file", default=None, help="agentic policy yaml path")
    parser.add_argument("--objective", choices=["single", "multi"], default=None)
    parser.add_argument("--enable-llm", action="store_true", help="enable LLM advisor fallback")
    parser.add_argument("--target-primitive", default=None, help="stop early when primitive is reached")
    parser.add_argument("--hardware", default=None, help="hardware adapter id or legacy mode override")
    parser.add_argument("--serial-port", default=None, help="override serial target port")
    parser.add_argument("--serial-timeout", type=float, default=None, help="override serial timeout")
    parser.add_argument("--serial-io", choices=["sync", "async"], default=None, help="serial IO mode override")
    parser.add_argument("--binding-file", default=None, help="override local hardware binding file path")
    parser.add_argument(
        "--require-preflight",
        action="store_true",
        help="require serial HIL preflight pass before campaign run",
    )
    parser.add_argument("--rerun-count", type=int, default=None, help="repeat same campaign N times")
    parser.add_argument("--fixed-seed", type=int, default=None, help="base seed for reproducibility runs")
    parser.add_argument(
        "--success-threshold",
        type=float,
        default=None,
        help="threshold used in reproducibility aggregate",
    )
    parser.add_argument(
        "--plugin-dir",
        action="append",
        default=[],
        help="additional plugin manifest directory (repeatable)",
    )
    parser.add_argument("--run-tag", default=None, help="optional run tag for reproducibility tracking")


def _add_hardware_management_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="configs/default.yaml", help="base config path")
    parser.add_argument("--template", default=None, help="campaign template yaml path")
    parser.add_argument("--target", default="stm32f3", help="target profile name")
    parser.add_argument("--config-mode", choices=["strict", "legacy"], default="strict")
    parser.add_argument("--hardware", default=None, help="preferred adapter id or legacy mode")
    parser.add_argument("--serial-port", default=None, help="probe only the given serial port")
    parser.add_argument("--binding-file", default=None, help="override local hardware binding file path")
