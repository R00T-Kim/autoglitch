from __future__ import annotations

from src.classifier import RuleBasedClassifier
from src.observer import BasicObserver
from src.types import FaultClass, RawResult


def _obs(serial: bytes, *, reset: bool = False, error_code: int | None = None):
    observer = BasicObserver()
    return observer.collect(
        RawResult(
            serial_output=serial,
            response_time=0.05,
            reset_detected=reset,
            error_code=error_code,
        )
    )


def test_classifier_detects_auth_bypass() -> None:
    classifier = RuleBasedClassifier()
    observation = _obs(b"AUTH BYPASS success: admin granted")

    assert classifier.classify(observation) == FaultClass.AUTH_BYPASS
    assert classifier.get_confidence() >= 0.8


def test_classifier_detects_reset_and_crash() -> None:
    classifier = RuleBasedClassifier()

    reset_obs = _obs(b"boot", reset=True)
    crash_obs = _obs(b"hard fault", error_code=1)

    assert classifier.classify(reset_obs) == FaultClass.RESET
    assert classifier.classify(crash_obs) == FaultClass.CRASH


def test_classifier_falls_back_to_normal() -> None:
    classifier = RuleBasedClassifier()
    observation = _obs(b"boot ok")

    assert classifier.classify(observation) == FaultClass.NORMAL
