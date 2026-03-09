"""Agentic, evaluation-suite, and knowledge CLI handlers."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .agentic import AgenticPlanner, PolicyEngine
from .cli_support import (
    _load_config,
    _load_run_config,
    _resolve_ai_mode,
    _resolve_policy_file,
    _validate_runtime_config,
    _write_json_report,
)
from .types import (
    ContextSnapshot,
    EvalSuitePayload,
    EvalSuiteResult,
    KnowledgeQueryPayload,
    KnowledgeRecord,
)

ExecuteCampaign = Callable[[argparse.Namespace], dict[str, Any]]


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
        config_policy=config.get("policy", {})
        if isinstance(config.get("policy", {}), dict)
        else {},
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
    payload: dict[str, Any] = {
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

    results: list[EvalSuiteResult] = []
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
                "target": str(output.get("template") or template),
                "primitive_repro_rate_mean": score,
                "stable_run_ratio": stable,
                "passed": passed,
                "raw": output,
            }
        )

    pass_count = len([item for item in results if item["passed"]])
    payload: EvalSuitePayload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "suite_size": len(results),
        "pass_count": pass_count,
        "pass_ratio": (pass_count / len(results)) if results else 0.0,
        "success_threshold": float(args.success_threshold),
        "results": results,
    }
    path = _write_json_report("eval_suite", payload)
    output = {**payload, "report": str(path)}
    print(json.dumps(output, indent=2, ensure_ascii=False))


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
    record: KnowledgeRecord = {
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
    scored: list[KnowledgeRecord] = []
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
    payload: KnowledgeQueryPayload = {
        "schema_version": 1,
        "store": str(store),
        "query": args.query,
        "top_k": top_k,
        "hits": hits,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
