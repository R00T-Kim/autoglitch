"""Extracted command handlers for the AUTOGLITCH CLI."""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from .agentic import AgenticPlanner, PolicyEngine
from .cli_runtime import _create_optimizer
from .cli_support import (
    _aggregate_rerun_results,
    _latest_report,
    _load_config,
    _load_plugin_registry,
    _load_run_config,
    _mean_reward_from_history,
    _read_jsonl,
    _resolve_ai_mode,
    _resolve_policy_file,
    _resolve_run_tag,
    _synthetic_reward,
    _validate_runtime_config,
    _write_json_report,
    compare_summary_to_report,
    summarize_trial_records,
)
from .optimizer import SB3Optimizer
from .types import ContextSnapshot

RunSingleCampaign = Callable[..., dict[str, Any]]
ExecuteCampaign = Callable[[argparse.Namespace], dict[str, Any]]


def run_benchmark_command(
    args: argparse.Namespace,
    *,
    run_single_campaign: RunSingleCampaign,
) -> None:
    config, template_name = _load_run_config(args)
    errors = _validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    algorithms = [item.strip().lower() for item in args.algorithms.split(",") if item.strip()]
    invalid_algorithms = [algo for algo in algorithms if algo not in {"bayesian", "rl"}]
    if invalid_algorithms:
        raise SystemExit(f"unsupported algorithms: {', '.join(invalid_algorithms)}")

    plugin_registry = _load_plugin_registry(config, getattr(args, "plugin_dir", []))
    run_tag = _resolve_run_tag(args, config)
    ai_mode = _resolve_ai_mode(args, config)
    objective_mode = str(getattr(args, "objective", "single")).lower()
    if objective_mode not in {"single", "multi"}:
        objective_mode = "single"

    results_by_algo: dict[str, list[dict[str, Any]]] = {algo: [] for algo in algorithms}
    base_seed = int(config.get("experiment", {}).get("fixed_seed") or config.get("experiment", {}).get("seed", 42))

    for algo_index, algo in enumerate(algorithms):
        for run_index in range(args.runs):
            run_seed = base_seed + run_index + (algo_index * 10000)
            run_id = f"bench_{algo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_index + 1:02d}"

            run_args = copy.copy(args)
            run_args.optimizer = algo
            run_args.enable_llm = False
            run_args.run_tag = run_tag
            run_args.ai_mode = ai_mode
            run_args.objective = objective_mode
            run_config = copy.deepcopy(config)
            run_config.setdefault("experiment", {})["seed"] = run_seed
            run_config.setdefault("logging", {})["run_tag"] = run_tag
            run_config.setdefault("ai", {})["mode"] = ai_mode
            run_config.setdefault("optimizer", {}).setdefault("bo", {})["objective_mode"] = objective_mode

            summary = run_single_campaign(
                run_config=run_config,
                args=run_args,
                run_seed=run_seed,
                run_id=run_id,
                trials=int(args.trials),
                target_primitive=None,
                plugin_registry=plugin_registry,
            )
            results_by_algo[algo].append(summary)

    aggregate_by_algo = {
        algo: _aggregate_rerun_results(runs, success_threshold=float(args.success_threshold))
        for algo, runs in results_by_algo.items()
    }

    winner = max(
        aggregate_by_algo.items(),
        key=lambda item: (
            item[1].get("primitive_repro_rate_mean", 0.0),
            item[1].get("success_rate_mean", 0.0),
        ),
    )[0]

    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "algorithms": algorithms,
        "ai_mode": ai_mode,
        "objective_mode": objective_mode,
        "run_tag": run_tag,
        "runs_per_algorithm": int(args.runs),
        "trials_per_run": int(args.trials),
        "results": results_by_algo,
        "aggregate": aggregate_by_algo,
        "winner": winner,
    }

    path = _write_json_report("comparison", payload)
    payload["comparison_report"] = str(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))



def train_rl_command(args: argparse.Namespace) -> None:
    config, template_name = _load_run_config(args)
    errors = _validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    run_tag = _resolve_run_tag(args, config)
    config = copy.deepcopy(config)
    config.setdefault("logging", {})["run_tag"] = run_tag
    param_space = config.get("glitch", {}).get("parameters", {})
    requested_backend = str(getattr(args, "rl_backend", "sb3"))
    rl_cfg = config.get("optimizer", {}).get("rl", {})
    total_steps = int(args.steps or rl_cfg.get("total_timesteps", 20_000))

    optimizer = _create_optimizer(
        optimizer_type="rl",
        config=config,
        param_space=param_space,
        bo_backend=None,
        rl_backend=requested_backend,
    )

    result: dict[str, Any]
    if isinstance(optimizer, SB3Optimizer):
        result = optimizer.train(steps=total_steps)
    else:
        for _ in range(total_steps):
            params = optimizer.suggest()
            reward = _synthetic_reward(params)
            optimizer.observe(params, reward, context={"source": "offline_train"})
        result = {
            "schema_version": 1,
            "optimizer": "rl",
            "backend_requested": requested_backend,
            "backend_in_use": "lite",
            "steps_run": total_steps,
            "observed_steps": int(getattr(optimizer, "n_trials", total_steps)),
            "evaluation": {
                "episodes": min(100, total_steps),
                "mean_reward": _mean_reward_from_history(optimizer),
            },
        }

    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "run_tag": run_tag,
        "requested_backend": requested_backend,
        "result": result,
    }
    path = _write_json_report("rl_train", payload)
    payload["report"] = str(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))



def eval_rl_command(args: argparse.Namespace) -> None:
    config, template_name = _load_run_config(args)
    errors = _validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    run_tag = _resolve_run_tag(args, config)
    config = copy.deepcopy(config)
    config.setdefault("logging", {})["run_tag"] = run_tag
    requested_backend = str(getattr(args, "rl_backend", "sb3"))
    param_space = config.get("glitch", {}).get("parameters", {})

    optimizer = _create_optimizer(
        optimizer_type="rl",
        config=config,
        param_space=param_space,
        bo_backend=None,
        rl_backend=requested_backend,
    )

    checkpoint_loaded: str | None = None
    if args.checkpoint and isinstance(optimizer, SB3Optimizer):
        optimizer.load_checkpoint(args.checkpoint)
        checkpoint_loaded = str(args.checkpoint)

    if isinstance(optimizer, SB3Optimizer):
        evaluation = optimizer.evaluate(episodes=int(args.episodes))
        backend_in_use = optimizer.backend_in_use
    else:
        rewards = []
        for _ in range(max(1, int(args.episodes))):
            rewards.append(_synthetic_reward(optimizer.suggest()))
        evaluation = {
            "episodes": max(1, int(args.episodes)),
            "mean_reward": float(mean(rewards)) if rewards else 0.0,
            "min_reward": float(min(rewards)) if rewards else 0.0,
            "max_reward": float(max(rewards)) if rewards else 0.0,
        }
        backend_in_use = "lite"

    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "template": template_name,
        "target": config.get("target", {}).get("name", args.target),
        "run_tag": run_tag,
        "requested_backend": requested_backend,
        "backend_in_use": backend_in_use,
        "checkpoint_loaded": checkpoint_loaded,
        "evaluation": evaluation,
    }
    path = _write_json_report("rl_eval", payload)
    payload["report"] = str(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))



def planner_step_command(args: argparse.Namespace) -> None:
    config, template_name = _load_run_config(args)
    errors = _validate_runtime_config(config, mode=args.config_mode)
    if errors:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

    ai_mode = _resolve_ai_mode(args, config)
    planner = AgenticPlanner(
        mode=ai_mode,
        max_actions_per_cycle=int(config.get("ai", {}).get("max_actions_per_cycle", 3)),
    )
    policy = PolicyEngine.from_sources(
        config_policy=config.get("policy", {}) if isinstance(config.get("policy", {}), dict) else {},
        policy_file=_resolve_policy_file(args, config),
        ai_limits=config.get("ai", {}) if isinstance(config.get("ai", {}), dict) else {},
    )
    snapshot = ContextSnapshot(
        trial_index=max(1, int(args.trial_index)),
        window_size=max(1, int(args.window_size)),
        success_rate_window=max(0.0, min(1.0, float(args.success_rate))),
        primitive_rate_window=max(0.0, min(1.0, float(args.primitive_rate))),
        timeout_rate_window=max(0.0, min(1.0, float(args.timeout_rate))),
        reset_rate_window=max(0.0, min(1.0, float(args.reset_rate))),
        latency_p95_window=max(0.0, float(args.latency_p95)),
        optimizer_backend=str(config.get("optimizer", {}).get("type", "bayesian")),
        target_name=str(config.get("target", {}).get("name", args.target)),
    )
    proposal = planner.propose(snapshot=snapshot, config=config)
    verdict = policy.evaluate(proposal=proposal, current_config=config)
    payload = {
        "schema_version": 1,
        "template": template_name,
        "ai_mode": ai_mode,
        "snapshot": {
            "trial_index": snapshot.trial_index,
            "window_size": snapshot.window_size,
            "success_rate_window": snapshot.success_rate_window,
            "primitive_rate_window": snapshot.primitive_rate_window,
            "timeout_rate_window": snapshot.timeout_rate_window,
            "reset_rate_window": snapshot.reset_rate_window,
            "latency_p95_window": snapshot.latency_p95_window,
            "optimizer_backend": snapshot.optimizer_backend,
            "target_name": snapshot.target_name,
        },
        "proposal": {
            "proposal_id": proposal.proposal_id,
            "rationale": proposal.rationale,
            "confidence": proposal.confidence,
            "changes": proposal.changes,
        },
        "policy_verdict": {
            "accepted": verdict.accepted,
            "reasons": verdict.reasons,
            "normalized_changes": verdict.normalized_changes,
            "validation_stage": verdict.validation_stage,
            "effect_type_by_path": verdict.effect_type_by_path,
            "validation_status_by_path": verdict.validation_status_by_path,
        },
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))



def eval_suite_command(
    args: argparse.Namespace,
    *,
    execute_campaign: ExecuteCampaign,
) -> None:
    templates = [item.strip() for item in str(args.templates).split(",") if item.strip()]
    if not templates:
        raise SystemExit("no templates provided")

    results: list[dict[str, Any]] = []
    for template in templates:
        run_args = argparse.Namespace(
            config="configs/default.yaml",
            template=template,
            config_mode=args.config_mode,
            target="stm32f3",
            trials=None,
            optimizer=None,
            bo_backend=None,
            rl_backend=None,
            ai_mode=args.ai_mode,
            policy_file=args.policy_file,
            objective=None,
            enable_llm=False,
            target_primitive=None,
            hardware=None,
            serial_port=None,
            serial_timeout=None,
            serial_io=None,
            require_preflight=False,
            rerun_count=None,
            fixed_seed=None,
            success_threshold=args.success_threshold,
            run_tag=args.run_tag,
            plugin_dir=[],
        )
        output = execute_campaign(run_args)
        aggregate = output.get("aggregate", {})
        score = float(aggregate.get("primitive_repro_rate_mean", 0.0))
        stable = float(aggregate.get("stable_run_ratio", 0.0))
        passed = score >= float(args.success_threshold)
        results.append(
            {
                "template": template,
                "target": output.get("template") or template,
                "primitive_repro_rate_mean": score,
                "stable_run_ratio": stable,
                "passed": passed,
                "raw": output,
            }
        )

    pass_count = len([item for item in results if item["passed"]])
    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "suite_size": len(results),
        "pass_count": pass_count,
        "pass_ratio": (pass_count / len(results)) if results else 0.0,
        "success_threshold": float(args.success_threshold),
        "results": results,
    }
    path = _write_json_report("eval_suite", payload)
    payload["report"] = str(path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))



def kb_ingest_command(args: argparse.Namespace) -> None:
    config = _load_config(Path("configs/default.yaml"), "stm32f3")
    default_store = str(config.get("knowledge", {}).get("store_path", "data/knowledge/kb.jsonl"))
    store = Path(args.store or default_store)
    store.parent.mkdir(parents=True, exist_ok=True)

    content = ""
    if args.source_file:
        source = Path(args.source_file)
        if not source.exists():
            raise SystemExit(f"source file not found: {source}")
        content = source.read_text(encoding="utf-8")
    elif args.text:
        content = str(args.text)
    else:
        raise SystemExit("provide --source-file or --text")

    tags = [tag.strip() for tag in str(args.tags).split(",") if tag.strip()]
    record = {
        "id": f"kb_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        "title": args.title or (Path(args.source_file).name if args.source_file else "inline-note"),
        "tags": tags,
        "content": content,
        "created_at": datetime.now().isoformat(),
    }
    with store.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "schema_version": 1,
                "store": str(store),
                "ingested_id": record["id"],
                "title": record["title"],
                "tags": tags,
            },
            indent=2,
            ensure_ascii=False,
        )
    )



def kb_query_command(args: argparse.Namespace) -> None:
    config = _load_config(Path("configs/default.yaml"), "stm32f3")
    default_store = str(config.get("knowledge", {}).get("store_path", "data/knowledge/kb.jsonl"))
    top_k_default = int(config.get("knowledge", {}).get("retrieval_top_k", 5))
    top_k = max(1, int(args.top_k or top_k_default))

    store = Path(args.store or default_store)
    if not store.exists():
        raise SystemExit(f"knowledge store not found: {store}")

    query_terms = [term for term in str(args.query).lower().split() if term]
    scored: list[dict[str, Any]] = []
    with store.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = f"{row.get('title', '')} {row.get('content', '')}".lower()
            score = 0.0
            for term in query_terms:
                score += text.count(term)
            if score > 0:
                row["score"] = score
                scored.append(row)

    scored.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    hits = scored[:top_k]
    print(
        json.dumps(
            {
                "schema_version": 1,
                "store": str(store),
                "query": args.query,
                "top_k": top_k,
                "hits": hits,
            },
            indent=2,
            ensure_ascii=False,
        )
    )



def validate_config_command(args: argparse.Namespace) -> None:
    config, template_name = _load_run_config(args)
    plugin_registry = _load_plugin_registry(config, [])

    errors = _validate_runtime_config(config, mode=args.config_mode)
    payload = {
        "schema_version": 1,
        "template": template_name,
        "config_mode": args.config_mode,
        "valid": len(errors) == 0,
        "errors": errors,
        "plugin_count": len(plugin_registry.list()),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if errors:
        raise SystemExit(2)



def list_plugins_command(args: argparse.Namespace) -> None:
    registry = _load_plugin_registry({}, getattr(args, "plugin_dir", []))
    manifests = [manifest.to_dict() for manifest in registry.list(kind=args.kind)]
    print(json.dumps({"schema_version": 1, "plugins": manifests}, indent=2, ensure_ascii=False))



def replay_run_command(args: argparse.Namespace) -> None:
    log_path = Path(args.log)
    if not log_path.exists():
        raise SystemExit(f"log file not found: {log_path}")

    trials = _read_jsonl(log_path)
    replay_summary = summarize_trial_records(trials)

    output: dict[str, Any] = {
        "schema_version": 1,
        "log": str(log_path),
        "replay_summary": replay_summary,
    }

    if args.report:
        report_path = Path(args.report)
        if not report_path.exists():
            raise SystemExit(f"report file not found: {report_path}")

        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        output["report"] = str(report_path)
        output["comparison"] = compare_summary_to_report(replay_summary, report_payload)

    print(json.dumps(output, indent=2, ensure_ascii=False))



def show_report_command(args: argparse.Namespace) -> None:
    report_file = Path(args.file) if args.file else _latest_report(Path("experiments/results"))
    if report_file is None or not report_file.exists():
        raise SystemExit("No report found. Run `autoglitch run` first.")

    with report_file.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
