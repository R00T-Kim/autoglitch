from __future__ import annotations

from src.agentic.patcher import apply_policy_patch
from src.agentic.trace import DecisionTraceStore
from src.types import PlannerDecision, PlannerProposal, PolicyVerdict


class _Optimizer:
    def __init__(self) -> None:
        self.candidate_pool_size = 192
        self.objective_mode = "multi"


def test_apply_policy_patch_returns_effect_and_apply_metadata() -> None:
    optimizer = _Optimizer()
    config = {"optimizer": {"bo": {"candidate_pool_size": 192}}, "experiment": {"success_threshold": 0.3}}

    patch_meta = apply_policy_patch(
        config=config,
        optimizer=optimizer,
        normalized_changes={
            "optimizer.bo.candidate_pool_size": 220,
            "experiment.success_threshold": 0.45,
        },
    )

    assert patch_meta["effect_type_by_path"] == {
        "optimizer.bo.candidate_pool_size": "live",
        "experiment.success_threshold": "next_run",
    }
    assert patch_meta["apply_status_by_path"] == {
        "optimizer.bo.candidate_pool_size": "live_applied",
        "experiment.success_threshold": "config_updated",
    }
    assert patch_meta["live_applied"] == {"optimizer.bo.candidate_pool_size": 220}
    assert patch_meta["deferred_applied"] == {"experiment.success_threshold": 0.45}
    assert patch_meta["applied"]["experiment.success_threshold"] == 0.45


def test_decision_trace_store_includes_validation_and_apply_metadata() -> None:
    optimizer = _Optimizer()
    config = {"optimizer": {"bo": {"candidate_pool_size": 192}}, "experiment": {"success_threshold": 0.3}}
    proposal = PlannerProposal(
        proposal_id="proposal-1",
        mode="agentic_enforced",
        rationale="unit",
        confidence=0.9,
        changes={
            "optimizer.bo.candidate_pool_size": 220,
            "experiment.success_threshold": 0.45,
        },
    )
    verdict = PolicyVerdict(
        accepted=True,
        reasons=[],
        normalized_changes={
            "optimizer.bo.candidate_pool_size": 220,
            "experiment.success_threshold": 0.45,
        },
    )
    verdict.effect_type_by_path = {
        "optimizer.bo.candidate_pool_size": "live",
        "experiment.success_threshold": "next_run",
    }
    verdict.validation_status_by_path = {
        "optimizer.bo.candidate_pool_size": "validated",
        "experiment.success_threshold": "validated",
    }

    patch_meta = apply_policy_patch(
        config=config,
        optimizer=optimizer,
        normalized_changes=verdict.normalized_changes,
    )
    decision = PlannerDecision(
        trace_id="trace-1",
        proposal=proposal,
        verdict=verdict,
        applied=True,
        applied_changes=patch_meta["applied"],
        live_applied_changes=patch_meta["live_applied"],
        deferred_changes=patch_meta["deferred_applied"],
        apply_status_by_path=patch_meta["apply_status_by_path"],
    )

    payload = DecisionTraceStore().append(decision)

    assert payload["verdict"]["effect_type_by_path"] == {
        "optimizer.bo.candidate_pool_size": "live",
        "experiment.success_threshold": "next_run",
    }
    assert payload["verdict"]["validation_status_by_path"] == {
        "optimizer.bo.candidate_pool_size": "validated",
        "experiment.success_threshold": "validated",
    }
    assert payload["apply_status_by_path"] == {
        "optimizer.bo.candidate_pool_size": "live_applied",
        "experiment.success_threshold": "config_updated",
    }
    assert payload["apply_metadata"]["deferred_applied"] == {"experiment.success_threshold": 0.45}
