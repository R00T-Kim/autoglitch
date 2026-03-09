"""Policy engine for validating planner proposals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import yaml  # type: ignore[import-untyped]

from ..types import PlannerProposal, PolicyVerdict


@dataclass(frozen=True)
class FieldPolicySpec:
    pattern: str
    value_type: str
    effect: str = "live"
    choices: tuple[str, ...] = ()


class ValidatedChangeSet(dict[str, Any]):
    """Normalized change map plus policy metadata for tracing/debugging."""

    def __init__(
        self,
        initial: Mapping[str, Any] | None = None,
        *,
        effect_type_by_path: Mapping[str, str] | None = None,
        validation_status_by_path: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(initial or {})
        self.effect_type_by_path = dict(effect_type_by_path or {})
        self.validation_status_by_path = dict(validation_status_by_path or {})


FIELD_POLICY_SPECS: tuple[FieldPolicySpec, ...] = (
    FieldPolicySpec("optimizer.bo.candidate_pool_size", "int", effect="live"),
    FieldPolicySpec(
        "optimizer.bo.objective_mode", "str", effect="live", choices=("single", "multi")
    ),
    FieldPolicySpec("optimizer.bo.multi_objective_weights.*", "float", effect="live"),
    FieldPolicySpec("optimizer.bo.vectorized_heuristic", "bool", effect="live"),
    FieldPolicySpec("optimizer.rl.train_interval", "int", effect="live"),
    FieldPolicySpec("optimizer.rl.learning_rate", "float", effect="live"),
    FieldPolicySpec("experiment.success_threshold", "float", effect="next_run"),
)


@dataclass
class PolicyRuleSet:
    allowed_fields: list[str] = field(default_factory=list)
    hard_limits: dict[str, dict[str, float]] = field(default_factory=dict)
    reject_on_unknown_field: bool = True
    max_patch_delta: float = 0.5
    max_actions_per_cycle: int = 3


class PolicyEngine:
    """Validates planner changes against allowlist, value types, and numerical limits."""

    def __init__(self, ruleset: PolicyRuleSet):
        self.ruleset = ruleset

    @classmethod
    def from_sources(
        cls,
        *,
        config_policy: dict[str, Any] | None = None,
        policy_file: str | None = None,
        ai_limits: dict[str, Any] | None = None,
    ) -> PolicyEngine:
        policy_payload: dict[str, Any] = {}
        if isinstance(config_policy, dict):
            policy_payload = dict(config_policy)

        if policy_file:
            with open(policy_file, encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                policy_payload = _deep_merge(policy_payload, loaded)

        ai_limits = ai_limits or {}
        ruleset = PolicyRuleSet(
            allowed_fields=list(policy_payload.get("allowed_fields", _default_allowed_fields())),
            hard_limits=dict(policy_payload.get("hard_limits", {})),
            reject_on_unknown_field=bool(policy_payload.get("reject_on_unknown_field", True)),
            max_patch_delta=float(
                ai_limits.get("max_patch_delta", policy_payload.get("max_patch_delta", 0.5))
            ),
            max_actions_per_cycle=int(
                ai_limits.get(
                    "max_actions_per_cycle", policy_payload.get("max_actions_per_cycle", 3)
                )
            ),
        )
        return cls(ruleset=ruleset)

    def evaluate(self, proposal: PlannerProposal, current_config: dict[str, Any]) -> PolicyVerdict:
        reasons: list[str] = []
        normalized_changes = {str(path): value for path, value in proposal.changes.items()}
        coerced_changes: dict[str, Any] = {}
        effect_type_by_path: dict[str, str] = {}
        validation_status_by_path: dict[str, str] = {}

        if len(normalized_changes) > self.ruleset.max_actions_per_cycle:
            reasons.append("too_many_actions")

        for path, value in normalized_changes.items():
            if self.ruleset.reject_on_unknown_field and not self._is_allowed(path):
                reasons.append(f"field_not_allowed:{path}")
                effect_type_by_path[path] = "unknown"
                validation_status_by_path[path] = "field_not_allowed"
                continue

            spec = self._field_spec(path)
            if spec is None:
                reasons.append(f"field_spec_missing:{path}")
                effect_type_by_path[path] = "unknown"
                validation_status_by_path[path] = "field_spec_missing"
                continue

            effect_type_by_path[path] = spec.effect

            try:
                normalized_value = _coerce_value(value, spec)
            except ValueError as exc:
                reason = str(exc)
                reasons.append(f"{reason}:{path}")
                validation_status_by_path[path] = reason
                continue

            validation_status_by_path[path] = "validated"

            if path in self.ruleset.hard_limits:
                limits = self.ruleset.hard_limits[path]
                min_value = limits.get("min")
                max_value = limits.get("max")
                numeric_value = float(normalized_value)
                if min_value is not None and numeric_value < float(min_value):
                    reasons.append(f"below_min:{path}")
                    validation_status_by_path[path] = "below_min"
                if max_value is not None and numeric_value > float(max_value):
                    reasons.append(f"above_max:{path}")
                    validation_status_by_path[path] = "above_max"

            current_value = _read_dotted(current_config, path)
            if isinstance(current_value, float | int) and isinstance(normalized_value, float | int):
                delta = abs(float(normalized_value) - float(current_value))
                if abs(float(current_value)) > 1e-9:
                    delta /= abs(float(current_value))
                if delta > self.ruleset.max_patch_delta:
                    reasons.append(f"delta_exceeded:{path}")
                    validation_status_by_path[path] = "delta_exceeded"

            coerced_changes[path] = normalized_value

        accepted = len(reasons) == 0
        normalized_payload = ValidatedChangeSet(
            coerced_changes if accepted else {},
            effect_type_by_path=effect_type_by_path,
            validation_status_by_path=validation_status_by_path,
        )
        verdict = PolicyVerdict(
            accepted=accepted,
            reasons=reasons,
            normalized_changes=normalized_payload,
            validation_stage="policy",
            effect_type_by_path=effect_type_by_path,
            validation_status_by_path=validation_status_by_path,
        )
        return verdict

    def effect_for(self, dotted_path: str) -> str:
        spec = self._field_spec(dotted_path)
        return spec.effect if spec is not None else "unknown"

    def _field_spec(self, dotted_path: str) -> FieldPolicySpec | None:
        for spec in FIELD_POLICY_SPECS:
            if spec.pattern == dotted_path:
                return spec
            if spec.pattern.endswith(".*") and dotted_path.startswith(spec.pattern[:-2] + "."):
                return spec
        return None

    def _is_allowed(self, dotted_path: str) -> bool:
        if dotted_path in self.ruleset.allowed_fields:
            return True
        for allowed in self.ruleset.allowed_fields:
            if allowed.endswith(".*"):
                prefix = allowed[:-2]
                if dotted_path.startswith(prefix + "."):
                    return True
        return False


def _default_allowed_fields() -> list[str]:
    return [
        "optimizer.bo.candidate_pool_size",
        "optimizer.bo.objective_mode",
        "optimizer.bo.multi_objective_weights.*",
        "optimizer.bo.vectorized_heuristic",
        "optimizer.rl.train_interval",
        "optimizer.rl.learning_rate",
        "experiment.success_threshold",
    ]


def _coerce_value(value: Any, spec: FieldPolicySpec) -> Any:
    normalized: Any
    if spec.value_type == "int":
        normalized = _coerce_int(value)
    elif spec.value_type == "float":
        normalized = _coerce_float(value)
    elif spec.value_type == "bool":
        normalized = _coerce_bool(value)
    elif spec.value_type == "str":
        if not isinstance(value, str):
            raise ValueError("invalid_type")
        normalized = value
    else:  # pragma: no cover - defensive fallback
        raise ValueError("invalid_type")

    if spec.choices and str(normalized) not in spec.choices:
        raise ValueError("invalid_choice")
    return normalized


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid_type")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError as exc:
            raise ValueError("invalid_type") from exc
        if not parsed.is_integer():
            raise ValueError("invalid_type")
        return int(parsed)
    raise ValueError("invalid_type")


def _coerce_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("invalid_type")
    if isinstance(value, float | int):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as exc:
            raise ValueError("invalid_type") from exc
    raise ValueError("invalid_type")


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError("invalid_type")


def _read_dotted(payload: dict[str, Any], dotted_path: str) -> Any:
    node: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(node, dict):
            return None
        if part not in node:
            return None
        node = node[part]
    return node


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
