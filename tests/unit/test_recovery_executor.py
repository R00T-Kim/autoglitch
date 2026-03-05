from __future__ import annotations

import pytest

from src.runtime import CircuitBreaker, CircuitOpenError, RecoveryExecutor, RetryPolicy


def test_recovery_executor_retries_then_recovers() -> None:
    calls = {"count": 0}

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("temporary failure")
        return "ok"

    executor = RecoveryExecutor(
        retry=RetryPolicy(max_attempts=3, initial_backoff_s=0.0, max_backoff_s=0.0),
        breaker=CircuitBreaker(failure_threshold=5, recovery_timeout_s=1.0),
    )

    result, meta = executor.execute(flaky)

    assert result == "ok"
    assert calls["count"] == 3
    assert meta["attempts"] == 3
    assert meta["recovered"] is True
    assert executor.breaker.state == "closed"


def test_recovery_executor_opens_circuit_after_failures() -> None:
    executor = RecoveryExecutor(
        retry=RetryPolicy(max_attempts=1, initial_backoff_s=0.0, max_backoff_s=0.0),
        breaker=CircuitBreaker(failure_threshold=2, recovery_timeout_s=60.0),
    )

    def always_fail() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        executor.execute(always_fail)
    with pytest.raises(RuntimeError):
        executor.execute(always_fail)

    with pytest.raises(CircuitOpenError):
        executor.execute(always_fail)
