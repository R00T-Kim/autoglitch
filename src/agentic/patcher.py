"""Patch applier for policy-approved planner changes."""
from __future__ import annotations

from typing import Any, Dict


def apply_policy_patch(
    *,
    config: Dict[str, Any],
    optimizer: Any,
    normalized_changes: Dict[str, Any],
) -> Dict[str, Any]:
    applied: Dict[str, Any] = {}
    live_applied: Dict[str, Any] = {}

    for path, value in normalized_changes.items():
        _write_dotted(config, path, value)
        applied[path] = value
        if _apply_to_optimizer_runtime(optimizer, path, value):
            live_applied[path] = value

    return {
        "applied": applied,
        "live_applied": live_applied,
    }


def _write_dotted(payload: Dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    node = payload
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


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
