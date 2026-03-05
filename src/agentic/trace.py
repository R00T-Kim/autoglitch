"""Decision trace persistence for agentic mode."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from ..types import PlannerDecision


class DecisionTraceStore:
    """Accumulates planner decisions and writes a JSON report."""

    def __init__(self) -> None:
        self._items: List[Dict[str, Any]] = []

    def append(self, decision: PlannerDecision) -> Dict[str, Any]:
        payload = _to_jsonable(asdict(decision))
        self._items.append(payload)
        return payload

    def snapshot(self) -> List[Dict[str, Any]]:
        return list(self._items)

    def write_report(
        self,
        *,
        output_dir: str = "experiments/results",
        prefix: str = "agentic_trace",
    ) -> Path:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
        path.write_text(json.dumps(self._items, indent=2, ensure_ascii=False), encoding="utf-8")
        return path


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
