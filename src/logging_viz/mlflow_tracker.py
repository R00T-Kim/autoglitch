"""Optional MLflow tracking integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MLflowTracker:
    """Thin wrapper that keeps MLflow optional at runtime."""

    enabled: bool = False
    tracking_uri: str | None = None
    experiment_name: str = "autoglitch"

    def __post_init__(self) -> None:
        self._mlflow = None
        self._active = False
        self.run_id: str | None = None
        self.disabled_reason: str | None = None

        if not self.enabled:
            return

        try:
            import mlflow
        except ModuleNotFoundError:
            self.enabled = False
            self.disabled_reason = "mlflow package not installed"
            logger.warning("MLflow disabled: %s", self.disabled_reason)
            return

        self._mlflow = mlflow
        if self.tracking_uri:
            self._mlflow.set_tracking_uri(self.tracking_uri)

    def start_run(
        self,
        *,
        run_name: str,
        tags: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        nested: bool = False,
    ) -> None:
        if not self.enabled or self._mlflow is None:
            return

        self._mlflow.set_experiment(self.experiment_name)
        self._mlflow.start_run(run_name=run_name, tags=dict(tags or {}), nested=nested)
        active = self._mlflow.active_run()
        self.run_id = active.info.run_id if active else None
        self._active = True

        if params:
            sanitized = {str(k): _to_primitive(v) for k, v in params.items()}
            self._mlflow.log_params(sanitized)

    def log_metrics(self, metrics: Mapping[str, float], step: int = 0) -> None:
        if not self.enabled or self._mlflow is None or not self._active:
            return

        sanitized = {str(k): float(v) for k, v in metrics.items()}
        self._mlflow.log_metrics(sanitized, step=step)

    def log_artifact(self, path: str | Path) -> None:
        if not self.enabled or self._mlflow is None or not self._active:
            return
        self._mlflow.log_artifact(str(path))

    def end_run(self, status: str = "FINISHED") -> None:
        if not self.enabled or self._mlflow is None or not self._active:
            return
        self._mlflow.end_run(status=status)
        self._active = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "tracking_uri": self.tracking_uri,
            "experiment_name": self.experiment_name,
            "run_id": self.run_id,
            "disabled_reason": self.disabled_reason,
        }


def _to_primitive(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
