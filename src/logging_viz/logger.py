"""실험 로그 기록/요약 유틸리티."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

import numpy as np

from ..types import CampaignResult, TrialResult


class ExperimentLogger:
    """Trial 결과를 JSONL로 저장하고 campaign 요약/manifest를 생성한다."""

    def __init__(self, output_dir: str = "experiments/logs", run_id: str | None = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
        self.log_path = self.output_dir / f"{self.run_id}.jsonl"

    def log_trial(self, trial: TrialResult) -> None:
        payload = _to_jsonable(trial)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def write_campaign_summary(
        self,
        campaign: CampaignResult,
        output_dir: str = "experiments/results",
    ) -> Path:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        summary_path = target_dir / f"{campaign.campaign_id}_{self.run_id}.json"
        payload: Dict[str, Any] = {
            "schema_version": 2,
            "campaign_id": campaign.campaign_id,
            "run_id": self.run_id,
            "n_trials": campaign.n_trials,
            "success_rate": campaign.success_rate,
            "primitive_repro_rate": campaign.primitive_repro_rate,
            "time_to_first_primitive": campaign.time_to_first_primitive,
            "fault_distribution": {
                fault.name: count for fault, count in campaign.fault_distribution.items()
            },
            "primitive_distribution": {
                primitive.name: count
                for primitive, count in campaign.primitive_distribution.items()
            },
            "config": campaign.config,
        }

        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

        return summary_path

    def write_run_manifest(
        self,
        config: Dict[str, Any],
        output_dir: str = "experiments/results",
        plugin_snapshot: Iterable[Dict[str, Any]] | None = None,
    ) -> Path:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        config_json = json.dumps(_to_jsonable(config), sort_keys=True, ensure_ascii=False)
        config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()

        payload: Dict[str, Any] = {
            "schema_version": 1,
            "created_at": datetime.now().isoformat(),
            "run_id": self.run_id,
            "config_version": int(config.get("config_version", 1)),
            "config_hash_sha256": config_hash,
            "target": config.get("target", {}),
            "optimizer": config.get("optimizer", {}),
            "plugins": list(plugin_snapshot or []),
        }

        path = target_dir / f"manifest_{self.run_id}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

        return path


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))

    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")

    if hasattr(value, "name") and hasattr(value, "value"):
        return value.name

    if isinstance(value, datetime):
        return value.isoformat()

    return value
