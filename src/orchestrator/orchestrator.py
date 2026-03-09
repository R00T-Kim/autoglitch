"""실험 오케스트레이터 - closed-loop 글리칭 자동화의 핵심."""

from __future__ import annotations

import logging
from enum import Enum, auto

from ..runtime import CircuitOpenError, RecoveryExecutor
from ..safety import SafetyController, SafetyViolation
from ..types import (
    CampaignResult,
    ExecutionMetadata,
    ExploitPrimitive,
    ExploitPrimitiveType,
    FaultClass,
    GlitchParameters,
    RawResult,
    TrialResult,
)

logger = logging.getLogger(__name__)


class OrchestratorState(Enum):
    INIT = auto()
    CONFIGURE = auto()
    GLITCH = auto()
    OBSERVE = auto()
    CLASSIFY = auto()
    MAP = auto()
    FEEDBACK = auto()
    DONE = auto()


class ExperimentOrchestrator:
    """Closed-loop 글리칭 실험 오케스트레이터."""

    def __init__(
        self,
        optimizer,
        hardware,
        observer,
        classifier,
        mapper,
        logger_viz,
        llm_advisor=None,
        config: dict | None = None,
        safety_controller: SafetyController | None = None,
        recovery_executor: RecoveryExecutor | None = None,
    ):
        self.optimizer = optimizer
        self.hardware = hardware
        self.observer = observer
        self.classifier = classifier
        self.mapper = mapper
        self.logger_viz = logger_viz
        self.llm_advisor = llm_advisor
        self.config = config or {}
        self.safety_controller = safety_controller
        self.recovery_executor = recovery_executor
        self.state = OrchestratorState.INIT
        self._trial_count = 0
        self._last_recovery_meta: dict = {"attempts": 1, "recovered": False}

    def run_trial(self) -> TrialResult:
        """단일 글리치 시도 실행"""
        self.state = OrchestratorState.CONFIGURE
        params = self.optimizer.suggest()

        safety_note = "none"
        if self.safety_controller is not None:
            params = self.safety_controller.sanitize_params(params)
            try:
                self.safety_controller.pre_trial(params)
            except SafetyViolation as exc:
                safety_note = f"blocked:{exc}"
                logger.warning("Safety pre-trial blocked request: %s", exc)
                # 차단 시 파라미터를 다시 안전범위 중앙값으로 대체
                params = self._fallback_safe_params(params)
                self.safety_controller.pre_trial(params)

        self.state = OrchestratorState.GLITCH
        raw_result, recovery_meta, execution = self._safe_execute(params)
        self._last_recovery_meta = recovery_meta
        if self.safety_controller is not None:
            self.safety_controller.post_trial()

        self.state = OrchestratorState.OBSERVE
        observation = self.observer.collect(raw_result)

        self.state = OrchestratorState.CLASSIFY
        if execution.status == "ok":
            fault_class = self.classifier.classify(observation)
        else:
            fault_class = FaultClass.UNKNOWN

        self.state = OrchestratorState.MAP
        if execution.status == "ok":
            primitive = self.mapper.map(fault_class, observation)
        else:
            primitive = ExploitPrimitive(
                type=ExploitPrimitiveType.NONE,
                confidence=0.0,
                description=f"execution_{execution.status}",
            )

        self.state = OrchestratorState.FEEDBACK
        if execution.status == "ok":
            reward = self._compute_reward(fault_class, primitive)
            self.optimizer.observe(
                params,
                reward,
                context={
                    "fault_class": fault_class.name,
                    "primitive": primitive.type.name,
                    "trial_id": self._trial_count + 1,
                    "safety": safety_note,
                    "recovery": recovery_meta,
                    "response_time": raw_result.response_time,
                    "reset_detected": raw_result.reset_detected,
                    "error_code": raw_result.error_code,
                    "execution_status": execution.status,
                },
            )

        self._trial_count += 1
        trial = TrialResult(
            trial_id=self._trial_count,
            parameters=params,
            observation=observation,
            fault_class=fault_class,
            primitive=primitive,
            execution=execution,
            metadata={
                "target": self.config.get("target", {}).get("name", "unknown"),
                "run_id": self.config.get("run_id", "local"),
                "error_category": self._categorize_error(fault_class, execution.status),
                "seed": self.config.get("experiment", {}).get("seed"),
                "repro_tag": self.config.get("repro_tag", "default"),
                "safety": safety_note,
                "recovery": recovery_meta,
            },
        )
        self.logger_viz.log_trial(trial)

        return trial

    def run_campaign(self, n_trials: int, target_primitive=None) -> CampaignResult:
        """실험 캠페인 실행 (N회 반복)"""
        campaign = CampaignResult(
            campaign_id=f"campaign_{self._trial_count + 1}",
            config=self.config,
        )

        if self.llm_advisor:
            strategy = self.llm_advisor.suggest_search_strategy(
                target_info=self.config.get("target")
            )
            logger.info("LLM suggested strategy: %s", strategy)

        for i in range(n_trials):
            trial = self.run_trial()
            campaign.trials.append(trial)

            if target_primitive and trial.primitive.type == target_primitive:
                logger.info("Target primitive %s achieved at trial %s", target_primitive, i + 1)
                break

            if self.llm_advisor and (i + 1) % 100 == 0:
                hypothesis = self.llm_advisor.generate_hypothesis(campaign.trials[-100:])
                logger.info("LLM hypothesis at trial %s: %s", i + 1, hypothesis)

        self.state = OrchestratorState.DONE
        return campaign

    def _safe_execute(self, params) -> tuple[RawResult, dict, ExecutionMetadata]:
        if self.recovery_executor is None:
            try:
                result = self.hardware.execute(params)
                return (
                    result,
                    {"attempts": 1, "recovered": False, "circuit_state_after": "disabled"},
                    ExecutionMetadata(
                        status="ok",
                        origin="hardware",
                        attempts=1,
                        recovered=False,
                        circuit_state_after="disabled",
                    ),
                )
            except Exception as exc:  # pragma: no cover - defensive path
                logger.exception("Hardware execution failed: %s", exc)
                return (
                    RawResult(
                        serial_output=f"hardware_error:{exc}".encode("utf-8", errors="replace"),
                        response_time=0.0,
                        reset_detected=False,
                        error_code=999,
                    ),
                    {
                        "attempts": 1,
                        "recovered": False,
                        "last_error": str(exc),
                        "circuit_state_after": "disabled",
                    },
                    ExecutionMetadata(
                        status="infra_failure",
                        origin="synthetic",
                        attempts=1,
                        recovered=False,
                        circuit_state_after="disabled",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    ),
                )

        try:
            result, meta = self.recovery_executor.execute(lambda: self.hardware.execute(params))
            return (
                result,
                meta,
                ExecutionMetadata(
                    status="ok",
                    origin="recovery" if bool(meta.get("recovered", False)) else "hardware",
                    attempts=int(meta.get("attempts", 1)),
                    recovered=bool(meta.get("recovered", False)),
                    circuit_state_after=str(meta.get("circuit_state_after", "closed")),
                    error_message=str(meta.get("last_error", "")) or None,
                ),
            )
        except CircuitOpenError as exc:
            logger.warning("Circuit breaker open: %s", exc)
            return (
                RawResult(
                    serial_output=f"circuit_open:{exc}".encode("utf-8", errors="replace"),
                    response_time=0.0,
                    reset_detected=False,
                    error_code=998,
                ),
                {
                    "attempts": 0,
                    "recovered": False,
                    "last_error": str(exc),
                    "circuit_state_after": "open",
                },
                ExecutionMetadata(
                    status="blocked",
                    origin="recovery",
                    attempts=0,
                    recovered=False,
                    circuit_state_after="open",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive path
            logger.exception("Hardware execution failed after retries: %s", exc)
            state = self.recovery_executor.breaker.state
            return (
                RawResult(
                    serial_output=f"hardware_error:{exc}".encode("utf-8", errors="replace"),
                    response_time=0.0,
                    reset_detected=False,
                    error_code=997,
                ),
                {
                    "attempts": self.recovery_executor.retry.max_attempts,
                    "recovered": False,
                    "last_error": str(exc),
                    "circuit_state_after": state,
                },
                ExecutionMetadata(
                    status="infra_failure",
                    origin="recovery",
                    attempts=int(self.recovery_executor.retry.max_attempts),
                    recovered=False,
                    circuit_state_after=str(state),
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                ),
            )

    def _fallback_safe_params(self, params: GlitchParameters) -> GlitchParameters:
        if self.safety_controller is None:
            return params
        limits = self.safety_controller.limits
        return GlitchParameters(
            width=(limits.width_min + limits.width_max) / 2.0,
            offset=(limits.offset_min + limits.offset_max) / 2.0,
            voltage=0.0,
            repeat=max(limits.repeat_min, min(limits.repeat_max, params.repeat)),
            ext_offset=params.ext_offset,
        )

    @staticmethod
    def _compute_reward(fault_class: FaultClass, primitive: ExploitPrimitive) -> float:
        """보상 함수: fault class와 primitive에 기반"""
        base_rewards = {
            FaultClass.NORMAL: 0.0,
            FaultClass.RESET: 0.1,
            FaultClass.CRASH: 0.3,
            FaultClass.INSTRUCTION_SKIP: 0.7,
            FaultClass.DATA_CORRUPTION: 0.6,
            FaultClass.AUTH_BYPASS: 1.0,
            FaultClass.UNKNOWN: 0.05,
        }
        reward = base_rewards.get(fault_class, 0.0)
        reward += primitive.confidence * 0.5
        return min(reward, 1.0)

    @staticmethod
    def _categorize_error(fault_class: FaultClass, execution_status: str = "ok") -> str:
        if execution_status == "infra_failure":
            return "infra_failure"
        if execution_status == "blocked":
            return "execution_blocked"
        if fault_class in (FaultClass.RESET, FaultClass.CRASH):
            return "runtime_failure"
        if fault_class in (FaultClass.INSTRUCTION_SKIP, FaultClass.DATA_CORRUPTION):
            return "fault_injection"
        if fault_class == FaultClass.AUTH_BYPASS:
            return "security_impact"
        if fault_class == FaultClass.UNKNOWN:
            return "unknown"
        return "none"
