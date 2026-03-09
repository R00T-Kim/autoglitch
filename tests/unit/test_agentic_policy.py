from __future__ import annotations

from src.agentic import AgenticPlanner, PolicyEngine, apply_policy_patch
from src.types import ContextSnapshot


def _snapshot() -> ContextSnapshot:
    return ContextSnapshot(
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


def test_policy_engine_rejects_unknown_field() -> None:
    policy = PolicyEngine.from_sources(
        config_policy={
            "allowed_fields": ["optimizer.bo.candidate_pool_size"],
            "reject_on_unknown_field": True,
        },
        policy_file=None,
        ai_limits={"max_patch_delta": 1.0, "max_actions_per_cycle": 3},
    )
    planner = AgenticPlanner(mode="agentic_enforced", max_actions_per_cycle=3)
    proposal = planner.propose(_snapshot(), {"optimizer": {"bo": {"candidate_pool_size": 192}}})
    proposal.changes["hardware.mode"] = "serial"  # 강제 금지 필드

    verdict = policy.evaluate(
        proposal, current_config={"optimizer": {"bo": {"candidate_pool_size": 192}}}
    )
    assert verdict.accepted is False
    assert any(reason == "field_not_allowed:hardware.mode" for reason in verdict.reasons)


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
    planner = AgenticPlanner(mode="agentic_enforced", max_actions_per_cycle=1)
    proposal = planner.propose(_snapshot(), {"optimizer": {"bo": {"candidate_pool_size": 192}}})
    proposal.changes = {"optimizer.bo.candidate_pool_size": 220}

    verdict = policy.evaluate(
        proposal, current_config={"optimizer": {"bo": {"candidate_pool_size": 192}}}
    )
    assert verdict.accepted is True
    assert verdict.normalized_changes["optimizer.bo.candidate_pool_size"] == 220
    assert verdict.validation_stage == "policy"
    assert verdict.effect_type_by_path["optimizer.bo.candidate_pool_size"] == "live"
    assert verdict.validation_status_by_path["optimizer.bo.candidate_pool_size"] == "validated"


def test_policy_engine_rejects_bad_type_with_validation_metadata() -> None:
    policy = PolicyEngine.from_sources(
        config_policy={
            "allowed_fields": ["optimizer.bo.candidate_pool_size"],
            "reject_on_unknown_field": True,
        },
        policy_file=None,
        ai_limits={"max_patch_delta": 1.0, "max_actions_per_cycle": 3},
    )
    planner = AgenticPlanner(mode="agentic_enforced", max_actions_per_cycle=1)
    proposal = planner.propose(_snapshot(), {"optimizer": {"bo": {"candidate_pool_size": 192}}})
    proposal.changes = {"optimizer.bo.candidate_pool_size": "oops"}

    verdict = policy.evaluate(
        proposal, current_config={"optimizer": {"bo": {"candidate_pool_size": 192}}}
    )

    assert verdict.accepted is False
    assert any(
        reason == "invalid_type:optimizer.bo.candidate_pool_size" for reason in verdict.reasons
    )
    assert verdict.effect_type_by_path["optimizer.bo.candidate_pool_size"] == "live"
    assert verdict.validation_status_by_path["optimizer.bo.candidate_pool_size"] == "invalid_type"


def test_apply_policy_patch_marks_next_run_and_live_effects() -> None:
    class OptimizerStub:
        def __init__(self) -> None:
            self.candidate_pool_size = 128

    optimizer = OptimizerStub()
    config = {
        "optimizer": {"bo": {"candidate_pool_size": 128}},
        "experiment": {"success_threshold": 0.2},
    }

    patch_meta = apply_policy_patch(
        config=config,
        optimizer=optimizer,
        normalized_changes={
            "optimizer.bo.candidate_pool_size": 160,
            "experiment.success_threshold": 0.45,
        },
    )

    assert patch_meta["live_applied"]["optimizer.bo.candidate_pool_size"] == 160
    assert patch_meta["deferred_applied"]["experiment.success_threshold"] == 0.45
    assert patch_meta["effect_type_by_path"]["experiment.success_threshold"] == "next_run"
    assert patch_meta["apply_status_by_path"]["experiment.success_threshold"] == "config_updated"
    assert optimizer.candidate_pool_size == 160
