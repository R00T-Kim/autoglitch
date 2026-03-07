"""AUTOGLITCH 핵심 데이터 타입 정의"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, TypedDict

import numpy as np


class FaultClass(Enum):
    """결함 주입 결과 분류 taxonomy"""

    NORMAL = auto()
    RESET = auto()
    CRASH = auto()
    INSTRUCTION_SKIP = auto()
    DATA_CORRUPTION = auto()
    AUTH_BYPASS = auto()
    UNKNOWN = auto()


class ExploitPrimitiveType(Enum):
    """익스플로잇 가능한 프리미티브 타입"""

    CONTROL_FLOW_HIJACK = auto()
    AUTH_CHECK_BYPASS = auto()
    MEMORY_READ = auto()
    MEMORY_WRITE = auto()
    PRIVILEGE_ESCALATION = auto()
    CODE_EXECUTION = auto()
    NONE = auto()


class RuntimeSummaryPayload(TypedDict):
    total_seconds: float
    throughput_trials_per_second: float


class LatencySummaryPayload(TypedDict):
    mean_seconds: float
    p95_seconds: float
    max_seconds: float


class ReproducibilityPayload(TypedDict):
    config_hash_sha256: str | None
    git_sha: str | None
    git_dirty: bool | None
    python_version: str | None
    platform: str | None


class ObjectiveSummaryPayload(TypedDict):
    mode: str
    multi_objective_weights: dict[str, float]


class AgenticSummaryPayload(TypedDict):
    mode: str
    event_count: int
    policy_reject_count: int
    agentic_interventions: int


class TrainingSummaryPayload(TypedDict):
    optimizer_backend: str | None
    observed_steps: int | None
    total_timesteps: int | None


class CampaignSummaryPayload(TypedDict):
    schema_version: int
    campaign_id: str
    run_id: str
    run_tag: str | None
    n_trials: int
    success_rate: float
    primitive_repro_rate: float
    time_to_first_primitive: int | None
    runtime: RuntimeSummaryPayload
    latency: LatencySummaryPayload
    error_breakdown: dict[str, int]
    fault_distribution: dict[str, int]
    primitive_distribution: dict[str, int]
    pareto_front: list[dict[str, Any]]
    config: dict[str, Any]
    reproducibility: ReproducibilityPayload
    objective_summary: ObjectiveSummaryPayload
    agentic: AgenticSummaryPayload
    decision_trace: list[dict[str, Any]]
    training: TrainingSummaryPayload
    optimizer_runtime: dict[str, Any]
    mlflow: dict[str, Any]


class RunManifestPayload(TypedDict):
    schema_version: int
    created_at: str
    run_id: str
    config_version: int
    config_hash_sha256: str
    runtime_fingerprint: dict[str, Any]
    run_tag: str | None
    target: dict[str, Any]
    optimizer: dict[str, Any]
    plugins: list[dict[str, Any]]


class RLEvaluationPayload(TypedDict):
    episodes: int
    mean_reward: float
    min_reward: float
    max_reward: float


class RLTrainResultPayload(TypedDict):
    schema_version: int
    optimizer: str
    backend_requested: str
    backend_in_use: str
    steps_run: int
    observed_steps: int
    checkpoint: str | None
    evaluation: RLEvaluationPayload


class RLTrainReportPayload(TypedDict):
    schema_version: int
    created_at: str
    template: str | None
    target: str
    run_tag: str | None
    requested_backend: str
    result: RLTrainResultPayload
    report: str


class RLEvalReportPayload(TypedDict):
    schema_version: int
    created_at: str
    template: str | None
    target: str
    run_tag: str | None
    requested_backend: str
    backend_in_use: str
    checkpoint_loaded: str | None
    evaluation: RLEvaluationPayload
    report: str


class EvalSuiteResult(TypedDict):
    template: str
    target: str
    primitive_repro_rate_mean: float
    stable_run_ratio: float
    passed: bool
    raw: dict[str, Any]


class EvalSuitePayload(TypedDict):
    schema_version: int
    created_at: str
    suite_size: int
    pass_count: int
    pass_ratio: float
    success_threshold: float
    results: list[EvalSuiteResult]


class KnowledgeRecord(TypedDict, total=False):
    id: str
    title: str
    tags: list[str]
    content: str
    created_at: str
    score: float


class KnowledgeQueryPayload(TypedDict):
    schema_version: int
    store: str
    query: str
    top_k: int
    hits: list[KnowledgeRecord]


@dataclass
class GlitchParameters:
    """글리치 파라미터"""

    width: float
    offset: float
    voltage: float = 0.0
    repeat: int = 1
    ext_offset: float = 0.0

    def to_array(self) -> np.ndarray:
        return np.array(
            [self.width, self.offset, self.voltage, self.repeat, self.ext_offset],
            dtype=float,
        )

    @classmethod
    def from_array(cls, arr: np.ndarray) -> GlitchParameters:
        if len(arr) < 4:
            raise ValueError("GlitchParameters.from_array requires at least 4 values")

        return cls(
            width=float(arr[0]),
            offset=float(arr[1]),
            voltage=float(arr[2]),
            repeat=int(arr[3]),
            ext_offset=float(arr[4]) if len(arr) >= 5 else 0.0,
        )


@dataclass
class RawResult:
    """하드웨어로부터의 원시 결과"""

    serial_output: bytes
    response_time: float
    reset_detected: bool
    error_code: int | None = None


@dataclass
class Observation:
    """전처리된 관측 결과"""

    raw: RawResult
    features: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    waveform: np.ndarray | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ExploitPrimitive:
    """익스플로잇 프리미티브"""

    type: ExploitPrimitiveType
    confidence: float = 0.0
    description: str = ""


@dataclass
class TrialResult:
    """단일 시도 결과"""

    trial_id: int
    parameters: GlitchParameters
    observation: Observation
    fault_class: FaultClass
    primitive: ExploitPrimitive
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextSnapshot:
    """Agentic planner 입력 스냅샷."""

    trial_index: int
    window_size: int
    success_rate_window: float
    primitive_rate_window: float
    timeout_rate_window: float
    reset_rate_window: float
    latency_p95_window: float
    optimizer_backend: str
    target_name: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class PlannerProposal:
    """Planner가 생성한 구조화된 제안."""

    proposal_id: str
    mode: str
    rationale: str
    confidence: float
    changes: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class PolicyVerdict:
    """정책 엔진 검증 결과."""

    accepted: bool
    reasons: list[str] = field(default_factory=list)
    normalized_changes: dict[str, Any] = field(default_factory=dict)
    validation_stage: str = "policy"
    effect_type_by_path: dict[str, str] = field(default_factory=dict)
    validation_status_by_path: dict[str, str] = field(default_factory=dict)


@dataclass
class PlannerDecision:
    """Proposal -> Policy -> Apply 결과 체인."""

    trace_id: str
    proposal: PlannerProposal
    verdict: PolicyVerdict
    applied: bool
    applied_changes: dict[str, Any] = field(default_factory=dict)
    live_applied_changes: dict[str, Any] = field(default_factory=dict)
    deferred_changes: dict[str, Any] = field(default_factory=dict)
    apply_status_by_path: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ReproEvalResult:
    """재현성 벤치 평가 요약."""

    suite_name: str
    target: str
    success_rate_mean: float
    primitive_repro_rate_mean: float
    stable_run_ratio: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CampaignResult:
    """실험 캠페인 전체 결과"""

    campaign_id: str
    trials: list[TrialResult] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    planner_events: list[dict[str, Any]] = field(default_factory=list)
    policy_reject_count: int = 0
    agentic_interventions: int = 0

    @property
    def n_trials(self) -> int:
        return len(self.trials)

    @property
    def success_rate(self) -> float:
        """NORMAL/RESET/UNKNOWN을 제외한 fault 비율"""
        if not self.trials:
            return 0.0
        successes = sum(
            1
            for t in self.trials
            if t.fault_class not in (FaultClass.NORMAL, FaultClass.RESET, FaultClass.UNKNOWN)
        )
        return successes / len(self.trials)

    @property
    def fault_distribution(self) -> dict[FaultClass, int]:
        dist: dict[FaultClass, int] = {}
        for trial in self.trials:
            dist[trial.fault_class] = dist.get(trial.fault_class, 0) + 1
        return dist

    @property
    def primitive_distribution(self) -> dict[ExploitPrimitiveType, int]:
        dist: dict[ExploitPrimitiveType, int] = {}
        for trial in self.trials:
            primitive_type = trial.primitive.type
            if primitive_type == ExploitPrimitiveType.NONE:
                continue
            dist[primitive_type] = dist.get(primitive_type, 0) + 1
        return dist

    @property
    def time_to_first_primitive(self) -> int | None:
        """첫 primitive 관측 trial id, 없으면 None"""
        for trial in self.trials:
            if trial.primitive.type != ExploitPrimitiveType.NONE:
                return trial.trial_id
        return None

    @property
    def primitive_repro_rate(self) -> float:
        """가장 많이 관측된 primitive의 재현 비율"""
        if not self.trials:
            return 0.0

        primitive_dist = self.primitive_distribution
        if not primitive_dist:
            return 0.0

        max_hits = max(primitive_dist.values())
        return max_hits / len(self.trials)

    @property
    def runtime_total_seconds(self) -> float:
        """Elapsed campaign duration based on trial timestamps."""
        if len(self.trials) < 2:
            return 0.0
        start = self.trials[0].timestamp
        end = self.trials[-1].timestamp
        return max(0.0, (end - start).total_seconds())

    @property
    def response_times_seconds(self) -> list[float]:
        values: list[float] = []
        for trial in self.trials:
            raw = getattr(trial.observation, "raw", None)
            if raw is None:
                continue
            value = float(getattr(raw, "response_time", 0.0))
            if value < 0:
                continue
            values.append(value)
        return values

    @property
    def latency_mean_seconds(self) -> float:
        values = self.response_times_seconds
        if not values:
            return 0.0
        return float(np.mean(values))

    @property
    def latency_p95_seconds(self) -> float:
        values = self.response_times_seconds
        if not values:
            return 0.0
        return float(np.percentile(np.array(values, dtype=float), 95))

    @property
    def latency_max_seconds(self) -> float:
        values = self.response_times_seconds
        if not values:
            return 0.0
        return float(max(values))

    @property
    def throughput_trials_per_second(self) -> float:
        runtime = self.runtime_total_seconds
        if runtime <= 0:
            return 0.0
        return float(self.n_trials / runtime)

    @property
    def pareto_front(self) -> list[dict[str, Any]]:
        """Non-dominated trials for (maximize signal score, minimize response latency)."""
        if not self.trials:
            return []

        candidates: list[dict[str, Any]] = []
        for trial in self.trials:
            response_time = float(getattr(trial.observation.raw, "response_time", 0.0))
            score = self._trial_signal_score(trial)
            candidates.append(
                {
                    "trial_id": trial.trial_id,
                    "fault_class": trial.fault_class.name,
                    "primitive": trial.primitive.type.name,
                    "confidence": float(trial.primitive.confidence),
                    "signal_score": score,
                    "response_time": response_time,
                }
            )

        front: list[dict[str, Any]] = []
        for idx, item in enumerate(candidates):
            dominated = False
            for jdx, other in enumerate(candidates):
                if idx == jdx:
                    continue
                if (
                    other["signal_score"] >= item["signal_score"]
                    and other["response_time"] <= item["response_time"]
                    and (
                        other["signal_score"] > item["signal_score"]
                        or other["response_time"] < item["response_time"]
                    )
                ):
                    dominated = True
                    break
            if not dominated:
                front.append(item)

        return sorted(front, key=lambda row: int(row["trial_id"]))

    @property
    def error_breakdown(self) -> dict[str, int]:
        """Distribution of orchestrator error categories from trial metadata."""
        dist: dict[str, int] = {}
        for trial in self.trials:
            category = "none"
            if isinstance(trial.metadata, dict):
                category = str(trial.metadata.get("error_category", "none"))
            dist[category] = dist.get(category, 0) + 1
        return dist

    @staticmethod
    def _trial_signal_score(trial: TrialResult) -> float:
        base_rewards = {
            FaultClass.NORMAL: 0.0,
            FaultClass.RESET: 0.1,
            FaultClass.CRASH: 0.3,
            FaultClass.INSTRUCTION_SKIP: 0.7,
            FaultClass.DATA_CORRUPTION: 0.6,
            FaultClass.AUTH_BYPASS: 1.0,
            FaultClass.UNKNOWN: 0.05,
        }
        reward = base_rewards.get(trial.fault_class, 0.0)
        reward += float(trial.primitive.confidence) * 0.5
        return min(1.0, float(reward))
