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
        mlflow_info: Dict[str, Any] | None = None,
        optimizer_info: Dict[str, Any] | None = None,
    ) -> Path:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        summary_path = target_dir / f"{campaign.campaign_id}_{self.run_id}.json"
        runtime_fingerprint = campaign.config.get("_runtime_fingerprint", {})
        optimizer_cfg = campaign.config.get("optimizer", {}) if isinstance(campaign.config, dict) else {}
        bo_cfg = optimizer_cfg.get("bo", {}) if isinstance(optimizer_cfg, dict) else {}
        ai_cfg = campaign.config.get("ai", {}) if isinstance(campaign.config, dict) else {}
        run_tag = campaign.config.get("run_tag") or campaign.config.get("logging", {}).get("run_tag")
        payload: Dict[str, Any] = {
            "schema_version": 6,
            "campaign_id": campaign.campaign_id,
            "run_id": self.run_id,
            "run_tag": run_tag,
            "n_trials": campaign.n_trials,
            "success_rate": campaign.success_rate,
            "primitive_repro_rate": campaign.primitive_repro_rate,
            "time_to_first_primitive": campaign.time_to_first_primitive,
            "runtime": {
                "total_seconds": campaign.runtime_total_seconds,
                "throughput_trials_per_second": campaign.throughput_trials_per_second,
            },
            "latency": {
                "mean_seconds": campaign.latency_mean_seconds,
                "p95_seconds": campaign.latency_p95_seconds,
                "max_seconds": campaign.latency_max_seconds,
            },
            "error_breakdown": campaign.error_breakdown,
            "fault_distribution": {
                fault.name: count for fault, count in campaign.fault_distribution.items()
            },
            "primitive_distribution": {
                primitive.name: count
                for primitive, count in campaign.primitive_distribution.items()
            },
            "pareto_front": campaign.pareto_front,
            "config": campaign.config,
            "reproducibility": {
                "config_hash_sha256": runtime_fingerprint.get("config_hash_sha256"),
                "git_sha": runtime_fingerprint.get("git_sha"),
                "git_dirty": runtime_fingerprint.get("git_dirty"),
                "python_version": runtime_fingerprint.get("python_version"),
                "platform": runtime_fingerprint.get("platform"),
            },
            "objective_summary": {
                "mode": bo_cfg.get("objective_mode", "single"),
                "multi_objective_weights": bo_cfg.get("multi_objective_weights", {}),
            },
            "agentic": {
                "mode": ai_cfg.get("mode", "off"),
                "event_count": len(campaign.planner_events),
                "policy_reject_count": campaign.policy_reject_count,
                "agentic_interventions": campaign.agentic_interventions,
            },
            "decision_trace": campaign.planner_events,
            "training": {
                "optimizer_backend": (optimizer_info or {}).get("backend_in_use"),
                "observed_steps": (optimizer_info or {}).get("observed_steps"),
                "total_timesteps": (optimizer_info or {}).get("total_timesteps"),
            },
            "optimizer_runtime": optimizer_info or {"enabled": False},
            "mlflow": mlflow_info or {"enabled": False},
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
            "runtime_fingerprint": config.get("_runtime_fingerprint", {}),
            "run_tag": config.get("run_tag") or config.get("logging", {}).get("run_tag"),
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
