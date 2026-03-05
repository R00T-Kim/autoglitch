from __future__ import annotations

from src.agentic import AgenticPlanner, PolicyEngine
from src.types import ContextSnapshot


def test_policy_engine_rejects_unknown_field() -> None:
    policy = PolicyEngine.from_sources(
        config_policy={
            "allowed_fields": ["optimizer.bo.candidate_pool_size"],
            "reject_on_unknown_field": True,
        },
        policy_file=None,
        ai_limits={"max_patch_delta": 1.0, "max_actions_per_cycle": 3},
    )
    snapshot = ContextSnapshot(
        trial_index=10,
        window_size=10,
        success_rate_window=0.01,
        primitive_rate_window=0.0,
        timeout_rate_window=0.0,
        reset_rate_window=0.0,
        latency_p95_window=0.2,
        optimizer_backend="heuristic",
        target_name="STM32F303",
    )
    planner = AgenticPlanner(mode="agentic_enforced", max_actions_per_cycle=3)
    proposal = planner.propose(snapshot, {"optimizer": {"bo": {"candidate_pool_size": 192}}})
    proposal.changes["hardware.mode"] = "serial"  # 강제 금지 필드

    verdict = policy.evaluate(proposal, current_config={"optimizer": {"bo": {"candidate_pool_size": 192}}})
    assert verdict.accepted is False
    assert any("field_not_allowed:hardware.mode" == reason for reason in verdict.reasons)


def test_policy_engine_accepts_allowed_change_under_limits() -> None:
    policy = PolicyEngine.from_sources(
        config_policy={
            "allowed_fields": ["optimizer.bo.candidate_pool_size"],
            "hard_limits": {"optimizer.bo.candidate_pool_size": {"min": 32, "max": 512}},
            "reject_on_unknown_field": True,
        },
        policy_file=None,
        ai_limits={"max_patch_delta": 1.0, "max_actions_per_cycle": 3},
    )
    snapshot = ContextSnapshot(
        trial_index=20,
        window_size=10,
        success_rate_window=0.01,
        primitive_rate_window=0.0,
        timeout_rate_window=0.0,
        reset_rate_window=0.0,
        latency_p95_window=0.1,
        optimizer_backend="heuristic",
        target_name="STM32F303",
    )
    planner = AgenticPlanner(mode="agentic_enforced", max_actions_per_cycle=1)
    proposal = planner.propose(snapshot, {"optimizer": {"bo": {"candidate_pool_size": 192}}})
    proposal.changes = {"optimizer.bo.candidate_pool_size": 220}

    verdict = policy.evaluate(proposal, current_config={"optimizer": {"bo": {"candidate_pool_size": 192}}})
    assert verdict.accepted is True
    assert verdict.normalized_changes["optimizer.bo.candidate_pool_size"] == 220
