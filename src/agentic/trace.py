"""Decision trace persistence for agentic mode."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from ..types import PlannerDecision


class DecisionTraceStore:
    """Accumulates planner decisions and writes a JSONL report."""

    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []

    def append(self, decision: PlannerDecision) -> dict[str, Any]:
        payload = cast(dict[str, Any], _to_jsonable(asdict(decision)))

        verdict_payload = payload.setdefault("verdict", {})
        effect_type_by_path = _extract_effect_type_by_path(decision)
        if effect_type_by_path:
            verdict_payload["effect_type_by_path"] = dict(effect_type_by_path)
            payload["effect_type_by_path"] = dict(effect_type_by_path)

        validation_status_by_path = _extract_validation_status_by_path(decision)
        if validation_status_by_path:
            verdict_payload["validation_status_by_path"] = dict(validation_status_by_path)
            payload["validation_status_by_path"] = dict(validation_status_by_path)

        validation_stage = getattr(decision.verdict, "validation_stage", None)
        if validation_stage:
            verdict_payload["validation_stage"] = validation_stage

        live_applied = _extract_mapping(
            getattr(decision, "live_applied_changes", {}),
            fallback=getattr(decision.applied_changes, "live_applied", {}),
        )
        deferred_applied = _extract_mapping(
            getattr(decision, "deferred_changes", {}),
            fallback=getattr(decision.applied_changes, "deferred_applied", {}),
        )
        apply_status_by_path = _extract_mapping(
            getattr(decision, "apply_status_by_path", {}),
            fallback=getattr(decision.applied_changes, "apply_status_by_path", {}),
        )
        apply_effect_type_by_path = _extract_mapping(
            getattr(decision.applied_changes, "effect_type_by_path", {}),
            fallback=effect_type_by_path,
        )

        payload["live_applied_changes"] = dict(live_applied)
        payload["deferred_changes"] = dict(deferred_applied)
        payload["apply_status_by_path"] = dict(apply_status_by_path)
        payload["apply_metadata"] = {
            "effect_type_by_path": dict(apply_effect_type_by_path),
            "apply_status_by_path": dict(apply_status_by_path),
            "live_applied": dict(live_applied),
            "deferred_applied": dict(deferred_applied),
        }

        self._items.append(payload)
        return payload

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._items)

    def write_report(
        self,
        *,
        output_dir: str = "experiments/results",
        prefix: str = "agentic_trace",
    ) -> Path:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jsonl"
        lines = [json.dumps(item, ensure_ascii=False) for item in self._items]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return path


def _extract_effect_type_by_path(decision: PlannerDecision) -> Mapping[str, str]:
    from_verdict = getattr(decision.verdict, "effect_type_by_path", {})
    if isinstance(from_verdict, Mapping) and from_verdict:
        return from_verdict

    from_changes = getattr(decision.verdict.normalized_changes, "effect_type_by_path", {})
    if isinstance(from_changes, Mapping):
        return from_changes
    return {}


def _extract_validation_status_by_path(decision: PlannerDecision) -> Mapping[str, str]:
    from_verdict = getattr(decision.verdict, "validation_status_by_path", {})
    if isinstance(from_verdict, Mapping) and from_verdict:
        return from_verdict

    from_changes = getattr(decision.verdict.normalized_changes, "validation_status_by_path", {})
    if isinstance(from_changes, Mapping):
        return from_changes
    return {}


def _extract_mapping(primary: Any, *, fallback: Any) -> Mapping[str, Any]:
    if isinstance(primary, Mapping) and primary:
        return primary
    if isinstance(fallback, Mapping):
        return fallback
    return {}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
