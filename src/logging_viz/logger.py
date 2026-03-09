"""실험 로그 기록/요약 유틸리티."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import numpy as np

from ..types import (
    ArtifactBundlePayload,
    CampaignResult,
    CampaignSummaryPayload,
    RunManifestPayload,
    TrialResult,
)


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
        mlflow_info: dict[str, Any] | None = None,
        optimizer_info: dict[str, Any] | None = None,
        component_plugins: dict[str, str] | None = None,
        artifact_bundle: str | None = None,
        bundle_manifest: str | None = None,
        benchmark: dict[str, Any] | None = None,
    ) -> Path:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        summary_path = target_dir / f"{campaign.campaign_id}_{self.run_id}.json"
        runtime_fingerprint = campaign.config.get("_runtime_fingerprint", {})
        optimizer_cfg = (
            campaign.config.get("optimizer", {}) if isinstance(campaign.config, dict) else {}
        )
        bo_cfg = optimizer_cfg.get("bo", {}) if isinstance(optimizer_cfg, dict) else {}
        ai_cfg = campaign.config.get("ai", {}) if isinstance(campaign.config, dict) else {}
        run_tag = campaign.config.get("run_tag") or campaign.config.get("logging", {}).get(
            "run_tag"
        )
        planner_backend = str(campaign.config.get("_planner_backend", "disabled"))
        advisor_backend = str(campaign.config.get("_advisor_backend", "disabled"))
        payload: CampaignSummaryPayload = {
            "schema_version": 8,
            "campaign_id": campaign.campaign_id,
            "run_id": self.run_id,
            "run_tag": run_tag,
            "n_trials": campaign.n_trials,
            "success_rate": campaign.success_rate,
            "primitive_repro_rate": campaign.primitive_repro_rate,
            "time_to_first_valid_fault": campaign.time_to_first_valid_fault,
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
            "execution_status_breakdown": campaign.execution_status_breakdown,
            "infra_failure_count": campaign.infra_failure_count,
            "blocked_count": campaign.blocked_count,
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
                "planner_backend": planner_backend,
                "advisor_backend": advisor_backend,
            },
            "decision_trace": campaign.planner_events,
            "training": {
                "optimizer_backend": (optimizer_info or {}).get("backend_in_use"),
                "observed_steps": (optimizer_info or {}).get("observed_steps"),
                "total_timesteps": (optimizer_info or {}).get("total_timesteps"),
            },
            "optimizer_runtime": optimizer_info or {"enabled": False},
            "mlflow": mlflow_info or {"enabled": False},
            "component_plugins": dict(component_plugins or {}),
            "artifact_bundle": artifact_bundle,
            "bundle_manifest": bundle_manifest,
            "benchmark": dict(benchmark or {}),
        }

        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

        return summary_path

    def write_run_manifest(
        self,
        config: dict[str, Any],
        output_dir: str = "experiments/results",
        plugin_snapshot: Iterable[dict[str, Any]] | None = None,
    ) -> Path:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        config_json = json.dumps(_to_jsonable(config), sort_keys=True, ensure_ascii=False)
        config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()

        payload: RunManifestPayload = {
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

    def bundle_dir(
        self,
        *,
        output_dir: str = "experiments/results",
        benchmark_id: str | None = None,
        target: str | None = None,
        backend: str | None = None,
    ) -> Path:
        target_dir = Path(output_dir) / "bundles"
        if benchmark_id:
            target_dir = target_dir / _safe_path_component(benchmark_id)
        if target:
            target_dir = target_dir / _safe_path_component(target)
        if backend:
            target_dir = target_dir / _safe_path_component(backend)
        return target_dir / _safe_path_component(self.run_id)

    def write_artifact_bundle(
        self,
        *,
        summary_path: Path,
        manifest_path: Path,
        log_path: Path,
        output_dir: str = "experiments/results",
        preflight_report: str | Path | dict[str, Any] | None = None,
        hardware_resolution: dict[str, Any] | None = None,
        benchmark: dict[str, Any] | None = None,
        lab: dict[str, Any] | None = None,
        component_plugins: dict[str, str] | None = None,
        rc_report: str | Path | dict[str, Any] | None = None,
    ) -> ArtifactBundlePayload:
        benchmark_payload = dict(benchmark or {})
        hardware_payload = dict(hardware_resolution or {})
        target_name = (
            str(benchmark_payload.get("target", "")).strip()
            or str(hardware_payload.get("target", "")).strip()
            or None
        )
        backend_name = (
            str(benchmark_payload.get("backend", "")).strip()
            or str(hardware_payload.get("binding", {}).get("adapter_id", "")).strip()
            or None
        )
        bundle_dir = self.bundle_dir(
            output_dir=output_dir,
            benchmark_id=str(benchmark_payload.get("benchmark_id", "")).strip() or None,
            target=target_name,
            backend=backend_name,
        )
        bundle_dir.mkdir(parents=True, exist_ok=True)

        files: dict[str, str] = {
            "campaign_summary": str(
                self._copy_into_bundle(summary_path, bundle_dir / "campaign_summary.json")
            ),
            "run_manifest": str(
                self._copy_into_bundle(manifest_path, bundle_dir / "run_manifest.json")
            ),
            "trial_log": str(
                self._copy_into_bundle(
                    log_path,
                    bundle_dir / "trial_log.jsonl",
                    allow_missing=True,
                )
            ),
        }

        if hardware_payload:
            hardware_path = bundle_dir / "hardware_resolution.json"
            hardware_path.write_text(
                json.dumps(hardware_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            files["hardware_resolution"] = str(hardware_path)

        preflight_path = _materialize_optional_json(
            bundle_dir=bundle_dir,
            filename="preflight.json",
            payload=preflight_report,
        )
        if preflight_path is not None:
            files["preflight"] = str(preflight_path)

        rc_path = _materialize_optional_json(
            bundle_dir=bundle_dir,
            filename="rc_validation.json",
            payload=rc_report,
        )
        if rc_path is not None:
            files["rc_validation"] = str(rc_path)

        metadata_path = bundle_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "created_at": datetime.now().isoformat(),
                    "run_id": self.run_id,
                    "benchmark": benchmark_payload,
                    "lab": dict(lab or {}),
                    "component_plugins": dict(component_plugins or {}),
                    "hardware_resolution": hardware_payload,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        files["metadata"] = str(metadata_path)

        notes_path = bundle_dir / "operator_notes.md"
        if not notes_path.exists():
            notes_path.write_text(
                "\n".join(
                    [
                        "# Operator Notes",
                        "",
                        "- board changes:",
                        "- wiring observations:",
                        "- power supply notes:",
                        "- anomalies:",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        files["operator_notes"] = str(notes_path)

        completeness = _bundle_completeness(files)
        manifest_payload = {
            "schema_version": 1,
            "created_at": datetime.now().isoformat(),
            "run_id": self.run_id,
            "bundle_dir": str(bundle_dir),
            "files": files,
            "completeness": completeness,
        }
        bundle_manifest_path = bundle_dir / "bundle_manifest.json"
        bundle_manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        files["bundle_manifest"] = str(bundle_manifest_path)

        for summary_target in (summary_path, bundle_dir / "campaign_summary.json"):
            _patch_json_file(
                summary_target,
                {
                    "artifact_bundle": str(bundle_dir),
                    "bundle_manifest": str(bundle_manifest_path),
                },
            )

        return {
            "schema_version": 1,
            "created_at": datetime.now().isoformat(),
            "run_id": self.run_id,
            "bundle_dir": str(bundle_dir),
            "manifest": str(bundle_manifest_path),
            "completeness": completeness,
            "files": files,
        }

    @staticmethod
    def _copy_into_bundle(
        source: Path,
        destination: Path,
        *,
        allow_missing: bool = False,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if allow_missing and not source.exists():
            destination.write_text("", encoding="utf-8")
            return destination
        shutil.copy2(source, destination)
        return destination


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(cast(Any, value)))

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


def _patch_json_file(path: Path, updates: dict[str, Any]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object in {path}")
    payload.update(_to_jsonable(updates))
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _materialize_optional_json(
    *,
    bundle_dir: Path,
    filename: str,
    payload: str | Path | dict[str, Any] | None,
) -> Path | None:
    if payload is None:
        return None
    destination = bundle_dir / filename
    if isinstance(payload, dict):
        destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return destination
    source = Path(payload)
    if not source.exists():
        return None
    shutil.copy2(source, destination)
    return destination


def _bundle_completeness(files: dict[str, str]) -> dict[str, bool]:
    required_files = (
        "campaign_summary",
        "run_manifest",
        "trial_log",
        "metadata",
        "hardware_resolution",
        "operator_notes",
    )
    required_ok = all(key in files for key in required_files)
    research_complete = required_ok and "preflight" in files
    rc_complete = research_complete and "rc_validation" in files
    return {
        "required_ok": required_ok,
        "research_complete": research_complete,
        "rc_complete": rc_complete,
    }


def _safe_path_component(value: str) -> str:
    cleaned = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value.strip()
    )
    return cleaned or "unknown"
