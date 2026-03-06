"""Patch applier for policy-approved planner changes."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class AppliedChangeSet(dict[str, Any]):
    """Applied change map plus runtime/apply metadata for trace consumers."""

    def __init__(
        self,
        initial: Mapping[str, Any] | None = None,
        *,
        effect_type_by_path: Mapping[str, str] | None = None,
        apply_status_by_path: Mapping[str, str] | None = None,
        live_applied: Mapping[str, Any] | None = None,
        deferred_applied: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(initial or {})
        self.effect_type_by_path = dict(effect_type_by_path or {})
        self.apply_status_by_path = dict(apply_status_by_path or {})
        self.live_applied = dict(live_applied or {})
        self.deferred_applied = dict(deferred_applied or {})


def apply_policy_patch(
    *,
    config: dict[str, Any],
    optimizer: Any,
    normalized_changes: Mapping[str, Any],
) -> dict[str, Any]:
    live_applied: dict[str, Any] = {}
    deferred_applied: dict[str, Any] = {}
    effect_type_by_path: dict[str, str] = {}
    apply_status_by_path: dict[str, str] = {}

    applied = AppliedChangeSet(
        effect_type_by_path=effect_type_by_path,
        apply_status_by_path=apply_status_by_path,
        live_applied=live_applied,
        deferred_applied=deferred_applied,
    )

    for path, value in normalized_changes.items():
        _write_dotted(config, path, value)
        applied[path] = value
        effect = _effect_for_path(path)
        effect_type_by_path[path] = effect
        if effect == "live" and _apply_to_optimizer_runtime(optimizer, path, value):
            live_applied[path] = value
            apply_status_by_path[path] = "live_applied"
        else:
            deferred_applied[path] = value
            apply_status_by_path[path] = "config_updated"

    return {
        "applied": applied,
        "live_applied": dict(live_applied),
        "deferred_applied": dict(deferred_applied),
        "effect_type_by_path": dict(effect_type_by_path),
        "apply_status_by_path": dict(apply_status_by_path),
    }


def _write_dotted(payload: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    node = payload
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _effect_for_path(dotted_path: str) -> str:
    if dotted_path == "experiment.success_threshold":
        return "next_run"
    return "live"


def _apply_to_optimizer_runtime(optimizer: Any, dotted_path: str, value: Any) -> bool:
    if dotted_path == "optimizer.bo.candidate_pool_size" and hasattr(optimizer, "candidate_pool_size"):
        optimizer.candidate_pool_size = max(1, int(value))
        return True

    if dotted_path == "optimizer.bo.objective_mode" and hasattr(optimizer, "objective_mode"):
        optimizer.objective_mode = str(value)
        return True

    if dotted_path == "optimizer.bo.vectorized_heuristic" and hasattr(optimizer, "vectorized_heuristic"):
        optimizer.vectorized_heuristic = bool(value)
        return True

    if dotted_path.startswith("optimizer.bo.multi_objective_weights.") and hasattr(optimizer, "multi_objective_weights"):
        key = dotted_path.split(".", 4)[-1]
        current = getattr(optimizer, "multi_objective_weights", {})
        if not isinstance(current, dict):
            current = {}
        current[str(key)] = float(value)
        optimizer.multi_objective_weights = current
        return True

    if dotted_path == "optimizer.rl.train_interval" and hasattr(optimizer, "train_interval"):
        optimizer.train_interval = max(1, int(value))
        return True

    if dotted_path == "optimizer.rl.learning_rate" and hasattr(optimizer, "learning_rate"):
        optimizer.learning_rate = max(1e-9, float(value))
        return True

    return False
