from __future__ import annotations

from src.optimizer import BayesianOptimizer


PARAM_SPACE = {
    "width": {"min": 0.0, "max": 50.0, "step": 0.1},
    "offset": {"min": 0.0, "max": 50.0, "step": 0.1},
    "voltage": {"min": -1.0, "max": 1.0},
    "repeat": {"min": 1, "max": 10},
}


def _reward(width: float, offset: float) -> float:
    return max(0.0, 1.0 - abs(width - 20.0) / 30.0 - abs(offset - 15.0) / 30.0)


def test_suggest_respects_bounds_and_step() -> None:
    optimizer = BayesianOptimizer(PARAM_SPACE, seed=123, n_initial=5, acquisition="ei")

    for _ in range(40):
        params = optimizer.suggest()

        assert 0.0 <= params.width <= 50.0
        assert 0.0 <= params.offset <= 50.0
        assert -1.0 <= params.voltage <= 1.0
        assert 1 <= params.repeat <= 10

        # step=0.1 quantization check
        assert abs((params.width * 10) - round(params.width * 10)) < 1e-6
        assert abs((params.offset * 10) - round(params.offset * 10)) < 1e-6

        optimizer.observe(params, _reward(params.width, params.offset))


def test_optimizer_updates_best_candidate() -> None:
    optimizer = BayesianOptimizer(PARAM_SPACE, seed=7, n_initial=3, acquisition="ucb")

    for _ in range(15):
        params = optimizer.suggest()
        optimizer.observe(params, _reward(params.width, params.offset))

    best = optimizer.get_best()
    assert best is not None

    best_params, best_reward = best
    assert best_reward >= 0.0
    assert isinstance(best_params.repeat, int)


def test_heuristic_backend_selection_is_respected() -> None:
    optimizer = BayesianOptimizer(
        PARAM_SPACE,
        seed=11,
        n_initial=2,
        acquisition="ei",
        backend="heuristic",
    )

    for _ in range(6):
        params = optimizer.suggest()
        optimizer.observe(params, _reward(params.width, params.offset))

    # 모델 학습 경로가 여러 번 호출된 뒤에도 heuristic 고정
    optimizer.suggest()
    assert optimizer.backend_in_use == "heuristic"


def test_vectorized_heuristic_exposes_telemetry() -> None:
    optimizer = BayesianOptimizer(
        PARAM_SPACE,
        seed=77,
        n_initial=2,
        acquisition="ei",
        backend="heuristic",
        candidate_pool_size=32,
        vectorized_heuristic=True,
    )

    for _ in range(8):
        params = optimizer.suggest()
        optimizer.observe(params, _reward(params.width, params.offset))

    _ = optimizer.suggest()
    telemetry = optimizer.telemetry_snapshot()

    assert telemetry["enabled"] is True
    assert telemetry["vectorized_heuristic"] is True
    assert telemetry["candidate_pool_size"] == 32
    assert telemetry["candidate_evaluations"] >= 32
    assert telemetry["latency_ms"]["suggest"]["count"] >= 1


def test_turbo_backend_falls_back_when_botorch_unavailable() -> None:
    optimizer = BayesianOptimizer(
        PARAM_SPACE,
        seed=99,
        n_initial=2,
        acquisition="ei",
        backend="turbo",
    )
    for _ in range(6):
        params = optimizer.suggest()
        optimizer.observe(params, _reward(params.width, params.offset))

    telemetry = optimizer.telemetry_snapshot()
    assert telemetry["backend_preference"] == "turbo"
    assert telemetry["backend_in_use"] in {"turbo", "heuristic", "botorch"}
    if telemetry["backend_in_use"] == "heuristic":
        assert telemetry["fallback_reason"] is not None


def test_qnehvi_multi_objective_metadata_is_reported() -> None:
    optimizer = BayesianOptimizer(
        PARAM_SPACE,
        seed=101,
        n_initial=2,
        acquisition="ei",
        backend="qnehvi",
        objective_mode="multi",
        multi_objective_weights={"reward": 1.0, "exploration": 0.6},
    )
    for _ in range(8):
        params = optimizer.suggest()
        optimizer.observe(params, _reward(params.width, params.offset))

    telemetry = optimizer.telemetry_snapshot()
    assert telemetry["objective_mode"] == "multi"
    assert telemetry["multi_objective_weights"]["exploration"] == 0.6
