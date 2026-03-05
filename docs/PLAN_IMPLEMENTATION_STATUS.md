# Plan Implementation Status (2026-03-05)

## ✅ Implemented in this cycle (Phase 1)

### 1) Async serial resilience
- `AsyncSerialCommandHardware` now uses a connection state machine:
  - `disconnected` → `connecting` → `connected` (+ `reconnecting`)
- Added persistent session reuse (`keep_open`) to reduce per-trial connection overhead.
- Added reconnect policy (`reconnect_attempts`, `reconnect_backoff_s`) for transient serial failures.
- Wired config knobs from `hardware.serial.*` into runtime adapter creation.

### 2) BO heuristic performance uplift
- `BayesianOptimizer` now supports vectorized heuristic acquisition scoring.
- Candidate pool evaluation is batched (numpy), reducing Python loop overhead.
- New config knobs:
  - `optimizer.bo.candidate_pool_size`
  - `optimizer.bo.vectorized_heuristic`

### 3) Optimizer telemetry and report schema v4
- Added optimizer telemetry snapshot (latency + fit/acquisition counters).
- `run` output includes `optimizer_telemetry`.
- Campaign summary upgraded to `schema_version: 4` with:
  - `runtime.throughput_trials_per_second`
  - `latency.mean_seconds / p95_seconds / max_seconds`
  - `pareto_front` (signal score vs response latency)
  - `optimizer_runtime`

### 4) Validation
- Added/updated tests for:
  - async serial persistence + reconnect
  - vectorized BO telemetry
  - schema v4 latency/Pareto summary
- Current test status: `54 passed`.

## 🔜 Next phase candidates
- SB3 true online/offline training path (callbacks/checkpoint/eval integration)
- TuRBO backend and constrained multi-objective mode
- HIL protocol gates (serial jitter/timeout envelopes + reproducibility stress tests)
