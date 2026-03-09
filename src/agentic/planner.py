"""Agentic planner that emits structured, policy-verifiable proposals."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..types import ContextSnapshot, PlannerProposal


class AgenticPlanner:
    """Deterministic heuristic planner for agentic modes.

    The planner intentionally emits JSON-like patches only. It never controls
    hardware directly.
    """

    def __init__(
        self,
        *,
        mode: str,
        max_actions_per_cycle: int = 3,
    ):
        self.mode = mode
        self.max_actions_per_cycle = max(1, int(max_actions_per_cycle))

    def propose(self, snapshot: ContextSnapshot, config: dict[str, Any]) -> PlannerProposal:
        changes: dict[str, Any] = {}
        rationale_parts: list[str] = []

        if snapshot.timeout_rate_window > 0.20:
            changes["optimizer.bo.candidate_pool_size"] = int(
                max(
                    32,
                    min(
                        512,
                        self._read_config(config, "optimizer.bo.candidate_pool_size", 192) * 0.8,
                    ),
                )
            )
            changes["optimizer.bo.multi_objective_weights.exploration"] = 0.2
            rationale_parts.append("timeout 높음 -> 탐색 강도 축소")

        if snapshot.success_rate_window < 0.10 and snapshot.timeout_rate_window <= 0.20:
            base_pool = self._read_config(config, "optimizer.bo.candidate_pool_size", 192)
            changes["optimizer.bo.candidate_pool_size"] = int(max(64, min(512, base_pool * 1.2)))
            changes["optimizer.bo.multi_objective_weights.exploration"] = 0.8
            changes["optimizer.bo.objective_mode"] = "multi"
            rationale_parts.append("성공률 낮음 -> exploration 확대")

        if snapshot.primitive_rate_window >= 0.30:
            changes["optimizer.bo.multi_objective_weights.reward"] = 1.2
            changes["experiment.success_threshold"] = float(
                max(
                    0.2,
                    min(
                        0.95, self._read_config(config, "experiment.success_threshold", 0.3) + 0.05
                    ),
                )
            )
            rationale_parts.append("primitive 관측 증가 -> exploit 비중 강화")

        if not changes:
            changes["optimizer.bo.multi_objective_weights.exploration"] = 0.4
            rationale_parts.append("변화 필요 낮음 -> baseline 유지")

        limited_changes: dict[str, Any] = {}
        for idx, (key, value) in enumerate(changes.items()):
            if idx >= self.max_actions_per_cycle:
                break
            limited_changes[key] = value

        confidence = self._estimate_confidence(snapshot)
        rationale = "; ".join(rationale_parts) if rationale_parts else "baseline heuristic"
        proposal_id = self._proposal_id(snapshot=snapshot, changes=limited_changes)
        return PlannerProposal(
            proposal_id=proposal_id,
            mode=self.mode,
            rationale=rationale,
            confidence=confidence,
            changes=limited_changes,
        )

    @staticmethod
    def _read_config(config: dict[str, Any], dotted_path: str, default: float | int) -> float:
        node: Any = config
        for part in dotted_path.split("."):
            if not isinstance(node, dict) or part not in node:
                return float(default)
            node = node[part]
        if isinstance(node, float | int):
            return float(node)
        return float(default)

    @staticmethod
    def _estimate_confidence(snapshot: ContextSnapshot) -> float:
        signal = (
            0.5 * snapshot.primitive_rate_window
            + 0.3 * snapshot.success_rate_window
            + 0.2 * (1.0 - min(1.0, snapshot.timeout_rate_window))
        )
        return float(max(0.05, min(0.98, signal)))

    @staticmethod
    def _proposal_id(*, snapshot: ContextSnapshot, changes: dict[str, Any]) -> str:
        raw = {
            "trial_index": snapshot.trial_index,
            "changes": changes,
        }
        encoded = json.dumps(raw, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]
        return f"proposal_{snapshot.trial_index}_{digest}"
