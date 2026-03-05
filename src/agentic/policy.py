"""Policy engine for validating planner proposals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import yaml

from ..types import PlannerProposal, PolicyVerdict


@dataclass
class PolicyRuleSet:
    allowed_fields: List[str] = field(default_factory=list)
    hard_limits: Dict[str, Dict[str, float]] = field(default_factory=dict)
    reject_on_unknown_field: bool = True
    max_patch_delta: float = 0.5
    max_actions_per_cycle: int = 3


class PolicyEngine:
    """Validates planner changes against allowlist and numerical limits."""

    def __init__(self, ruleset: PolicyRuleSet):
        self.ruleset = ruleset

    @classmethod
    def from_sources(
        cls,
        *,
        config_policy: Dict[str, Any] | None = None,
        policy_file: str | None = None,
        ai_limits: Dict[str, Any] | None = None,
    ) -> "PolicyEngine":
        policy_payload: Dict[str, Any] = {}
        if isinstance(config_policy, dict):
            policy_payload = dict(config_policy)

        if policy_file:
            with open(policy_file, "r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                policy_payload = _deep_merge(policy_payload, loaded)

        ai_limits = ai_limits or {}
        ruleset = PolicyRuleSet(
            allowed_fields=list(policy_payload.get("allowed_fields", _default_allowed_fields())),
            hard_limits=dict(policy_payload.get("hard_limits", {})),
            reject_on_unknown_field=bool(policy_payload.get("reject_on_unknown_field", True)),
            max_patch_delta=float(ai_limits.get("max_patch_delta", policy_payload.get("max_patch_delta", 0.5))),
            max_actions_per_cycle=int(
                ai_limits.get("max_actions_per_cycle", policy_payload.get("max_actions_per_cycle", 3))
            ),
        )
        return cls(ruleset=ruleset)

    def evaluate(self, proposal: PlannerProposal, current_config: Dict[str, Any]) -> PolicyVerdict:
        reasons: List[str] = []
        normalized_changes = {
            str(path): value
            for path, value in proposal.changes.items()
        }

        if len(normalized_changes) > self.ruleset.max_actions_per_cycle:
            reasons.append("too_many_actions")

        for path, value in normalized_changes.items():
            if self.ruleset.reject_on_unknown_field and not self._is_allowed(path):
                reasons.append(f"field_not_allowed:{path}")
                continue

            if path in self.ruleset.hard_limits and isinstance(value, float | int):
                limits = self.ruleset.hard_limits[path]
                min_value = limits.get("min")
                max_value = limits.get("max")
                numeric_value = float(value)
                if min_value is not None and numeric_value < float(min_value):
                    reasons.append(f"below_min:{path}")
                if max_value is not None and numeric_value > float(max_value):
                    reasons.append(f"above_max:{path}")

            current_value = _read_dotted(current_config, path)
            if isinstance(current_value, float | int) and isinstance(value, float | int):
                delta = abs(float(value) - float(current_value))
                if abs(float(current_value)) > 1e-9:
                    delta /= abs(float(current_value))
                if delta > self.ruleset.max_patch_delta:
                    reasons.append(f"delta_exceeded:{path}")

        accepted = len(reasons) == 0
        return PolicyVerdict(
            accepted=accepted,
            reasons=reasons,
            normalized_changes=normalized_changes if accepted else {},
        )

    def _is_allowed(self, dotted_path: str) -> bool:
        if dotted_path in self.ruleset.allowed_fields:
            return True
        for allowed in self.ruleset.allowed_fields:
            if allowed.endswith(".*"):
                prefix = allowed[:-2]
                if dotted_path.startswith(prefix + "."):
                    return True
        return False


def _default_allowed_fields() -> List[str]:
    return [
        "optimizer.bo.candidate_pool_size",
        "optimizer.bo.objective_mode",
        "optimizer.bo.multi_objective_weights.*",
        "optimizer.bo.vectorized_heuristic",
        "optimizer.rl.train_interval",
        "optimizer.rl.learning_rate",
        "experiment.success_threshold",
    ]


def _read_dotted(payload: Dict[str, Any], dotted_path: str) -> Any:
    node: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(node, dict):
            return None
        if part not in node:
            return None
        node = node[part]
    return node


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
