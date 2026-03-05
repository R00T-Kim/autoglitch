"""Retry and circuit-breaker execution utilities."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when circuit breaker blocks execution."""


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_s: float = 0.1
    max_backoff_s: float = 1.0
    backoff_multiplier: float = 2.0
    jitter_s: float = 0.0


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout_s: float = 10.0
    state: str = "closed"
    failure_count: int = 0
    opened_at: Optional[float] = None
    last_error: str = ""

    def before_call(self) -> None:
        if self.state != "open":
            return

        assert self.opened_at is not None
        elapsed = time.monotonic() - self.opened_at
        if elapsed >= self.recovery_timeout_s:
            self.state = "half_open"
            return

        raise CircuitOpenError(
            f"circuit open; retry in {self.recovery_timeout_s - elapsed:.2f}s"
        )

    def on_success(self) -> None:
        self.state = "closed"
        self.failure_count = 0
        self.opened_at = None
        self.last_error = ""

    def on_failure(self, error: Exception) -> None:
        self.failure_count += 1
        self.last_error = str(error)

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.opened_at = time.monotonic()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_s": self.recovery_timeout_s,
            "last_error": self.last_error,
        }


@dataclass
class RecoveryExecutor:
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "RecoveryExecutor":
        recovery_cfg = config.get("recovery", {})
        retry_cfg = recovery_cfg.get("retry", {})
        circuit_cfg = recovery_cfg.get("circuit_breaker", {})

        retry = RetryPolicy(
            max_attempts=int(retry_cfg.get("max_attempts", 3)),
            initial_backoff_s=float(retry_cfg.get("initial_backoff_s", 0.1)),
            max_backoff_s=float(retry_cfg.get("max_backoff_s", 1.0)),
            backoff_multiplier=float(retry_cfg.get("backoff_multiplier", 2.0)),
            jitter_s=float(retry_cfg.get("jitter_s", 0.0)),
        )

        breaker = CircuitBreaker(
            failure_threshold=int(circuit_cfg.get("failure_threshold", 5)),
            recovery_timeout_s=float(circuit_cfg.get("recovery_timeout_s", 10.0)),
        )
        return cls(retry=retry, breaker=breaker)

    def execute(self, fn: Callable[[], T]) -> tuple[T, Dict[str, Any]]:
        meta: Dict[str, Any] = {
            "attempts": 0,
            "recovered": False,
            "circuit_state_before": self.breaker.state,
            "circuit_state_after": self.breaker.state,
            "last_error": "",
        }

        self.breaker.before_call()

        delay = max(0.0, self.retry.initial_backoff_s)
        last_exc: Exception | None = None

        for attempt in range(1, max(1, self.retry.max_attempts) + 1):
            meta["attempts"] = attempt
            try:
                result = fn()
                self.breaker.on_success()
                meta["recovered"] = attempt > 1
                meta["circuit_state_after"] = self.breaker.state
                return result, meta
            except Exception as exc:  # pragma: no cover - exercised via tests
                last_exc = exc
                meta["last_error"] = str(exc)
                self.breaker.on_failure(exc)
                meta["circuit_state_after"] = self.breaker.state

                if attempt >= self.retry.max_attempts:
                    break

                if self.breaker.state == "open":
                    break

                sleep_s = delay
                if self.retry.jitter_s > 0:
                    sleep_s += random.uniform(0.0, self.retry.jitter_s)
                if sleep_s > 0:
                    time.sleep(sleep_s)
                delay = min(self.retry.max_backoff_s, delay * self.retry.backoff_multiplier)

        if last_exc is not None:
            raise last_exc

        raise RuntimeError("recovery executor failed without exception")
