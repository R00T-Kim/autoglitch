"""Strict configuration schema and validation helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class _BaseStrictModel(BaseModel):
    """Base model with strict typing while allowing forward-compatible keys."""

    model_config = ConfigDict(strict=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_non_extension_keys(cls, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload

        known_fields = set(cls.model_fields.keys())
        unknown = [
            str(key) for key in payload if key not in known_fields and not str(key).startswith("x_")
        ]
        if unknown:
            unknown_list = ", ".join(sorted(unknown))
            raise ValueError(f"unknown keys not allowed (use x_* for extensions): {unknown_list}")
        return payload


class RangeSpec(_BaseStrictModel):
    min: float | int
    max: float | int
    step: float | int | None = None

    @model_validator(mode="after")
    def _validate_bounds(self) -> "RangeSpec":
        if float(self.min) > float(self.max):
            raise ValueError("min must be <= max")
        if self.step is not None and float(self.step) <= 0:
            raise ValueError("step must be > 0")
        return self


class ExperimentConfig(_BaseStrictModel):
    name: str = "default"
    seed: int = 42
    max_trials: int = 10_000
    rerun_count: int = 1
    fixed_seed: int | None = None
    success_threshold: float = 0.3

    @model_validator(mode="after")
    def _validate_positive_values(self) -> "ExperimentConfig":
        if self.max_trials <= 0:
            raise ValueError("max_trials must be > 0")
        if self.rerun_count <= 0:
            raise ValueError("rerun_count must be > 0")
        if not 0.0 <= self.success_threshold <= 1.0:
            raise ValueError("success_threshold must be in [0, 1]")
        return self


class OptimizerBOConfig(_BaseStrictModel):
    n_initial: int = 50
    acquisition: str = "ei"
    backend: Literal["auto", "heuristic", "botorch", "turbo", "qnehvi"] = "auto"
    objective_mode: Literal["single", "multi"] = "single"
    multi_objective_weights: Dict[str, float] = Field(default_factory=dict)
    candidate_pool_size: int = 192
    vectorized_heuristic: bool = True

    @field_validator("n_initial", "candidate_pool_size")
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be > 0")
        return value

    @model_validator(mode="after")
    def _validate_multi_objective_weights(self) -> "OptimizerBOConfig":
        for key, value in self.multi_objective_weights.items():
            if not isinstance(key, str) or not key:
                raise ValueError("multi_objective_weights keys must be non-empty strings")
            if not isinstance(value, float | int):
                raise ValueError("multi_objective_weights values must be numeric")
            if float(value) < 0:
                raise ValueError("multi_objective_weights values must be >= 0")
        return self


class OptimizerRLConfig(_BaseStrictModel):
    algorithm: str = "ppo"
    learning_rate: float = 3e-4
    backend: Literal["lite", "sb3"] = "lite"
    total_timesteps: int = 20_000
    train_interval: int = 32
    checkpoint_interval: int = 5_000
    warmup_steps: int = 256
    eval_interval: int = 1_000
    save_best_only: bool = False
    checkpoint_dir: str = "experiments/results"

    @model_validator(mode="after")
    def _validate_positive_values(self) -> "OptimizerRLConfig":
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be > 0")
        if self.total_timesteps <= 0:
            raise ValueError("total_timesteps must be > 0")
        if self.train_interval <= 0:
            raise ValueError("train_interval must be > 0")
        if self.checkpoint_interval <= 0:
            raise ValueError("checkpoint_interval must be > 0")
        if self.warmup_steps < 0:
            raise ValueError("warmup_steps must be >= 0")
        if self.eval_interval <= 0:
            raise ValueError("eval_interval must be > 0")
        if not self.checkpoint_dir:
            raise ValueError("checkpoint_dir must not be empty")
        return self


class OptimizerConfig(_BaseStrictModel):
    type: Literal["bayesian", "rl"] = "bayesian"
    bo: OptimizerBOConfig = Field(default_factory=OptimizerBOConfig)
    rl: OptimizerRLConfig = Field(default_factory=OptimizerRLConfig)


class HardwareTargetConfig(_BaseStrictModel):
    type: str = "stm32f3"
    port: Optional[str] = None
    baudrate: int = 115_200
    timeout: float = 1.0

    @model_validator(mode="after")
    def _validate_target_values(self) -> "HardwareTargetConfig":
        if self.baudrate <= 0:
            raise ValueError("baudrate must be > 0")
        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")
        return self


class HardwareSerialPreflightConfig(_BaseStrictModel):
    enabled: bool = True
    probe_trials: int = 30
    max_timeout_rate: float = 0.05
    max_reset_rate: float = 0.10
    max_p95_latency_s: float = 0.50

    @model_validator(mode="after")
    def _validate_preflight(self) -> "HardwareSerialPreflightConfig":
        if self.probe_trials <= 0:
            raise ValueError("probe_trials must be > 0")
        for value, name in (
            (self.max_timeout_rate, "max_timeout_rate"),
            (self.max_reset_rate, "max_reset_rate"),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.max_p95_latency_s <= 0:
            raise ValueError("max_p95_latency_s must be > 0")
        return self


class HardwareSerialConfig(_BaseStrictModel):
    io_mode: Literal["sync", "async"] = "sync"
    keep_open: bool = True
    reconnect_attempts: int = 2
    reconnect_backoff_s: float = 0.05
    preflight: HardwareSerialPreflightConfig = Field(default_factory=HardwareSerialPreflightConfig)

    @model_validator(mode="after")
    def _validate_serial_runtime(self) -> "HardwareSerialConfig":
        if self.reconnect_attempts < 0:
            raise ValueError("reconnect_attempts must be >= 0")
        if self.reconnect_backoff_s < 0:
            raise ValueError("reconnect_backoff_s must be >= 0")
        return self


class HardwarePeripheralConfig(_BaseStrictModel):
    type: str = "none"
    port: str | None = None


class HardwareConfig(_BaseStrictModel):
    mode: Literal["mock", "serial"] = "mock"
    glitcher: HardwarePeripheralConfig = Field(default_factory=HardwarePeripheralConfig)
    target: HardwareTargetConfig = Field(default_factory=HardwareTargetConfig)
    oscilloscope: HardwarePeripheralConfig = Field(default_factory=HardwarePeripheralConfig)
    serial_command_template: str = (
        "GLITCH width={width:.3f} offset={offset:.3f} "
        "voltage={voltage:.3f} repeat={repeat:d} ext_offset={ext_offset:.3f}"
    )
    reset_command: str = ""
    trigger_command: str = ""
    serial: HardwareSerialConfig = Field(default_factory=HardwareSerialConfig)


class GlitchParametersConfig(_BaseStrictModel):
    width: RangeSpec
    offset: RangeSpec
    voltage: RangeSpec
    repeat: RangeSpec
    ext_offset: RangeSpec = Field(
        default_factory=lambda: RangeSpec(min=0.0, max=1_000_000.0, step=1.0)
    )

    @model_validator(mode="after")
    def _validate_ext_offset_bounds(self) -> "GlitchParametersConfig":
        if float(self.ext_offset.min) < 0:
            raise ValueError("ext_offset.min must be >= 0")
        if float(self.ext_offset.max) < 0:
            raise ValueError("ext_offset.max must be >= 0")
        return self


class GlitchConfig(_BaseStrictModel):
    parameters: GlitchParametersConfig


class SafetyConfig(_BaseStrictModel):
    width_min: float = 0.0
    width_max: float = 50.0
    offset_min: float = 0.0
    offset_max: float = 50.0
    voltage_abs_max: float = 1.0
    repeat_min: int = 1
    repeat_max: int = 10
    ext_offset_min: float = 0.0
    ext_offset_max: float = 1_000_000.0
    min_cooldown_s: float = 0.0
    max_trials_per_minute: int | None = None
    auto_throttle: bool = True

    @model_validator(mode="after")
    def _validate_safety(self) -> "SafetyConfig":
        if self.width_min > self.width_max:
            raise ValueError("width_min must be <= width_max")
        if self.offset_min > self.offset_max:
            raise ValueError("offset_min must be <= offset_max")
        if self.repeat_min > self.repeat_max:
            raise ValueError("repeat_min must be <= repeat_max")
        if self.ext_offset_min > self.ext_offset_max:
            raise ValueError("ext_offset_min must be <= ext_offset_max")
        if self.voltage_abs_max <= 0:
            raise ValueError("voltage_abs_max must be > 0")
        if self.ext_offset_min < 0:
            raise ValueError("ext_offset_min must be >= 0")
        if self.min_cooldown_s < 0:
            raise ValueError("min_cooldown_s must be >= 0")
        if self.max_trials_per_minute is not None and self.max_trials_per_minute <= 0:
            raise ValueError("max_trials_per_minute must be > 0")
        return self


class MLflowConfig(_BaseStrictModel):
    enabled: bool = False
    tracking_uri: str | None = None
    experiment_name: str = "autoglitch"


class LoggingConfig(_BaseStrictModel):
    level: str = "INFO"
    save_waveforms: bool = False
    mlflow_tracking_uri: str | None = None  # legacy key
    mlflow: MLflowConfig = Field(default_factory=MLflowConfig)
    run_tag: str | None = None
    store_env_fingerprint: bool = True


class PluginsConfig(_BaseStrictModel):
    manifest_dirs: List[str] = Field(default_factory=list)


class AIConfig(_BaseStrictModel):
    mode: Literal["off", "advisor", "agentic_shadow", "agentic_enforced"] = "off"
    provider: str = "local"
    model: str = "heuristic-planner-v1"
    planner_interval_trials: int = 50
    max_patch_delta: float = 0.5
    max_actions_per_cycle: int = 3
    confidence_threshold: float = 0.25
    fallback_on_policy_reject: bool = True

    @model_validator(mode="after")
    def _validate_ai(self) -> "AIConfig":
        if self.planner_interval_trials <= 0:
            raise ValueError("planner_interval_trials must be > 0")
        if self.max_patch_delta < 0:
            raise ValueError("max_patch_delta must be >= 0")
        if self.max_actions_per_cycle <= 0:
            raise ValueError("max_actions_per_cycle must be > 0")
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in [0, 1]")
        return self


class PolicyConfig(_BaseStrictModel):
    allowed_fields: List[str] = Field(default_factory=list)
    hard_limits: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    rate_limits: Dict[str, float] = Field(default_factory=dict)
    reject_on_unknown_field: bool = True
    max_patch_delta: float = 0.5
    max_actions_per_cycle: int = 3

    @model_validator(mode="after")
    def _validate_policy(self) -> "PolicyConfig":
        if self.max_patch_delta < 0:
            raise ValueError("max_patch_delta must be >= 0")
        if self.max_actions_per_cycle <= 0:
            raise ValueError("max_actions_per_cycle must be > 0")
        return self


class RecoveryRetryConfig(_BaseStrictModel):
    max_attempts: int = 3
    initial_backoff_s: float = 0.1
    max_backoff_s: float = 1.0
    backoff_multiplier: float = 2.0
    jitter_s: float = 0.0

    @model_validator(mode="after")
    def _validate_retry(self) -> "RecoveryRetryConfig":
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be > 0")
        if self.initial_backoff_s < 0:
            raise ValueError("initial_backoff_s must be >= 0")
        if self.max_backoff_s < 0:
            raise ValueError("max_backoff_s must be >= 0")
        if self.backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")
        if self.jitter_s < 0:
            raise ValueError("jitter_s must be >= 0")
        if self.max_backoff_s < self.initial_backoff_s:
            raise ValueError("max_backoff_s must be >= initial_backoff_s")
        return self


class RecoveryCircuitBreakerConfig(_BaseStrictModel):
    failure_threshold: int = 5
    recovery_timeout_s: float = 10.0

    @model_validator(mode="after")
    def _validate_breaker(self) -> "RecoveryCircuitBreakerConfig":
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be > 0")
        if self.recovery_timeout_s < 0:
            raise ValueError("recovery_timeout_s must be >= 0")
        return self


class RecoveryConfig(_BaseStrictModel):
    retry: RecoveryRetryConfig = Field(default_factory=RecoveryRetryConfig)
    circuit_breaker: RecoveryCircuitBreakerConfig = Field(
        default_factory=RecoveryCircuitBreakerConfig
    )


class KnowledgeConfig(_BaseStrictModel):
    enabled: bool = False
    store_path: str = "data/knowledge/kb.jsonl"
    retrieval_top_k: int = 5

    @model_validator(mode="after")
    def _validate_knowledge(self) -> "KnowledgeConfig":
        if self.retrieval_top_k <= 0:
            raise ValueError("retrieval_top_k must be > 0")
        if not self.store_path:
            raise ValueError("store_path must not be empty")
        return self


class TargetConfig(_BaseStrictModel):
    name: str
    family: str | None = None
    flash_size: str | None = None
    ram_size: str | None = None
    clock_freq: int | None = None
    interface: str | None = None
    baudrate: int | None = None
    reset_delay: float | None = None
    boot_delay: float | None = None
    firmware: str | None = None


class ClassifierConfig(_BaseStrictModel):
    model: str = "rule_based"
    fault_classes: List[str] = Field(default_factory=list)


class AutoglitchConfig(_BaseStrictModel):
    config_version: int = 2
    defaults: List[Any] = Field(default_factory=list)
    experiment: ExperimentConfig
    optimizer: OptimizerConfig
    glitch: GlitchConfig
    hardware: HardwareConfig
    target: TargetConfig
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    classifier: ClassifierConfig = Field(default_factory=ClassifierConfig)
    recovery: RecoveryConfig = Field(default_factory=RecoveryConfig)

    @field_validator("config_version")
    @classmethod
    def _validate_version(cls, value: int) -> int:
        if value != 2:
            raise ValueError("strict schema requires config_version: 2")
        return value

    @model_validator(mode="after")
    def _validate_parameter_relationships(self) -> "AutoglitchConfig":
        glitch = self.glitch.parameters

        if self.safety.width_min < float(glitch.width.min) or self.safety.width_max > float(
            glitch.width.max
        ):
            raise ValueError("safety.width range must be within glitch.parameters.width range")

        if self.safety.offset_min < float(glitch.offset.min) or self.safety.offset_max > float(
            glitch.offset.max
        ):
            raise ValueError("safety.offset range must be within glitch.parameters.offset range")

        repeat_min = int(glitch.repeat.min)
        repeat_max = int(glitch.repeat.max)
        if self.safety.repeat_min < repeat_min or self.safety.repeat_max > repeat_max:
            raise ValueError("safety.repeat range must be within glitch.parameters.repeat range")

        ext_offset_min = float(glitch.ext_offset.min)
        ext_offset_max = float(glitch.ext_offset.max)
        if (
            self.safety.ext_offset_min < ext_offset_min
            or self.safety.ext_offset_max > ext_offset_max
        ):
            raise ValueError(
                "safety.ext_offset range must be within glitch.parameters.ext_offset range"
            )

        voltage_abs = max(abs(float(glitch.voltage.min)), abs(float(glitch.voltage.max)))
        if self.safety.voltage_abs_max > voltage_abs:
            raise ValueError(
                "safety.voltage_abs_max must be <= glitch.parameters.voltage abs range"
            )

        return self


def parse_autoglitch_config(config: Dict[str, Any]) -> AutoglitchConfig:
    """Parse and return strongly-typed AUTOGLITCH configuration."""
    return cast(AutoglitchConfig, AutoglitchConfig.model_validate(config))


def validate_autoglitch_config(config: Dict[str, Any]) -> List[str]:
    """Validate config and return user-friendly error messages."""
    try:
        parse_autoglitch_config(config)
    except ValidationError as exc:
        errors: List[str] = []
        for item in exc.errors():
            loc = ".".join(str(part) for part in item.get("loc", []))
            msg = item.get("msg", "invalid value")
            if loc:
                errors.append(f"{loc}: {msg}")
            else:
                errors.append(msg)
        return errors

    return []
