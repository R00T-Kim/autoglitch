"""Agentic campaign helpers extracted from the CLI module."""
from __future__ import annotations

from typing import Any

import numpy as np

from .agentic import AgenticPlanner, DecisionTraceStore, PolicyEngine, apply_policy_patch
from .types import (
    CampaignResult,
    ContextSnapshot,
    ExploitPrimitiveType,
    PlannerDecision,
    PolicyVerdict,
)


def _run_campaign_agentic(
    *,
    orchestrator: Any,
    optimizer: Any,
    run_config: dict[str, Any],
    n_trials: int,
    target_primitive: ExploitPrimitiveType | None,
    ai_mode: str,
    policy_file: str | None,
) -> tuple[CampaignResult, dict[str, Any]]:
    ai_cfg = run_config.get("ai", {}) if isinstance(run_config.get("ai", {}), dict) else {}
    interval = max(1, int(ai_cfg.get("planner_interval_trials", 50)))
    confidence_threshold = float(ai_cfg.get("confidence_threshold", 0.25))
    planner = AgenticPlanner(
        mode=ai_mode,
        max_actions_per_cycle=int(ai_cfg.get("max_actions_per_cycle", 3)),
    )
    policy = PolicyEngine.from_sources(
        config_policy=run_config.get("policy", {}) if isinstance(run_config.get("policy", {}), dict) else {},
        policy_file=policy_file,
        ai_limits=ai_cfg,
    )
    trace_store = DecisionTraceStore()

    campaign = CampaignResult(
        campaign_id=f"campaign_{getattr(orchestrator, '_trial_count', 0) + 1}",
        config=run_config,
    )

    for idx in range(n_trials):
        trial = orchestrator.run_trial()
        campaign.trials.append(trial)

        if target_primitive and trial.primitive.type == target_primitive:
            break

        if (idx + 1) % interval != 0:
            continue

        snapshot = _build_context_snapshot(
            campaign=campaign,
            optimizer=optimizer,
            window_size=interval,
            run_config=run_config,
        )
        proposal = planner.propose(snapshot=snapshot, config=run_config)

        if proposal.confidence < confidence_threshold:
            verdict = PolicyVerdict(
                accepted=False,
                reasons=["below_confidence_threshold"],
                normalized_changes={},
                validation_stage="confidence_gate",
                effect_type_by_path={},
                validation_status_by_path={},
            )
        else:
            verdict = policy.evaluate(proposal=proposal, current_config=run_config)

        applied = False
        applied_changes: dict[str, Any] = {}
        live_applied_changes: dict[str, Any] = {}
        deferred_changes: dict[str, Any] = {}
        apply_status_by_path: dict[str, str] = {}
        if ai_mode == "agentic_enforced" and verdict.accepted:
            patch_meta = apply_policy_patch(
                config=run_config,
                optimizer=optimizer,
                normalized_changes=verdict.normalized_changes,
            )
            applied_changes = patch_meta.get("applied", {})
            live_applied_changes = patch_meta.get("live_applied", {})
            deferred_changes = patch_meta.get("deferred_applied", {})
            apply_status_by_path = patch_meta.get("apply_status_by_path", {})
            applied = bool(applied_changes)
        elif verdict.accepted:
            apply_status_by_path = {path: "shadow_only" for path in verdict.normalized_changes}

        decision = PlannerDecision(
            trace_id=f"trace_{idx + 1}_{len(campaign.planner_events) + 1}",
            proposal=proposal,
            verdict=verdict,
            applied=applied,
            applied_changes=applied_changes,
            live_applied_changes=live_applied_changes,
            deferred_changes=deferred_changes,
            apply_status_by_path=apply_status_by_path,
        )
        payload = trace_store.append(decision)
        campaign.planner_events.append(payload)
        if not verdict.accepted:
            campaign.policy_reject_count += 1
        if applied:
            campaign.agentic_interventions += 1

    trace_report = trace_store.write_report() if campaign.planner_events else None
    return campaign, {
        "mode": ai_mode,
        "events": campaign.planner_events,
        "policy_reject_count": campaign.policy_reject_count,
        "agentic_interventions": campaign.agentic_interventions,
        "trace_report": str(trace_report) if trace_report else None,
    }


def _build_context_snapshot(
    *,
    campaign: CampaignResult,
    optimizer: Any,
    window_size: int,
    run_config: dict[str, Any],
) -> ContextSnapshot:
    trials = campaign.trials[-max(1, int(window_size)) :]
    if not trials:
        return ContextSnapshot(
            trial_index=0,
            window_size=max(1, int(window_size)),
            success_rate_window=0.0,
            primitive_rate_window=0.0,
            timeout_rate_window=0.0,
            reset_rate_window=0.0,
            latency_p95_window=0.0,
            optimizer_backend=str(getattr(optimizer, "backend_in_use", type(optimizer).__name__)),
            target_name=str(run_config.get("target", {}).get("name", "unknown")),
        )

    total = float(len(trials))
    success_count = sum(
        1
        for trial in trials
        if trial.fault_class.name not in {"NORMAL", "RESET", "UNKNOWN"}
    )
    primitive_count = sum(1 for trial in trials if trial.primitive.type.name != "NONE")
    timeout_count = sum(1 for trial in trials if not trial.observation.raw.serial_output)
    reset_count = sum(1 for trial in trials if trial.observation.raw.reset_detected)
    latencies = [max(0.0, float(trial.observation.raw.response_time)) for trial in trials]
    latency_p95 = float(np.percentile(np.array(latencies, dtype=float), 95)) if latencies else 0.0

    return ContextSnapshot(
        trial_index=campaign.n_trials,
        window_size=len(trials),
        success_rate_window=success_count / total,
        primitive_rate_window=primitive_count / total,
        timeout_rate_window=timeout_count / total,
        reset_rate_window=reset_count / total,
        latency_p95_window=latency_p95,
        optimizer_backend=str(getattr(optimizer, "backend_in_use", type(optimizer).__name__)),
        target_name=str(run_config.get("target", {}).get("name", "unknown")),
    )
