# Plan Implementation Status (2026-03-06)

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
- Current test status (2026-03-06): `93 passed, 2 skipped`.

## 🔜 Next phase candidates
- SB3 true online/offline training path (callbacks/checkpoint/eval integration)
- TuRBO backend and constrained multi-objective mode
- HIL protocol gates (serial jitter/timeout envelopes + reproducibility stress tests)

## ✅ Additional implementation (Phase 1.5)
- Added `hil-preflight` CLI command for serial readiness probes.
- Added `--require-preflight` gate for `run`, `soak`, `queue-run`, `benchmark`.
- Added strict schema for `hardware.serial.preflight.*` thresholds.
- Hardened CI gates by removing lint/typecheck soft-fail settings.

## ✅ Additional implementation (Phase 2, 2026-03-06)
- RL train/eval software path added:
  - `train-rl` command for warmup training + checkpoint report
  - `eval-rl` command for checkpoint evaluation
- SB3 facade expanded with:
  - checkpoint save/load helpers
  - periodic evaluation and telemetry snapshot
  - warmup/eval/save-best config hooks
- BO config/backend expansion:
  - `optimizer.bo.backend`: `turbo`, `qnehvi` accepted
  - `optimizer.bo.objective_mode`: `single|multi`
  - `optimizer.bo.multi_objective_weights` added
- Reporting upgraded to `schema_version: 5`:
  - reproducibility fingerprint (`config_hash`, git/Python/platform)
  - objective summary
  - training summary
- Run tagging added (`--run-tag`, `logging.run_tag`) across run/queue/soak/benchmark.
- GitHub Actions security hardening:
  - `actions/checkout`, `actions/setup-python`, `github/codeql-action` full SHA pinning

## ✅ Additional implementation (Phase 3, 2026-03-06)
- Agentic control skeleton added:
  - `src/agentic/planner.py`, `policy.py`, `patcher.py`, `trace.py`
  - AI modes: `off`, `advisor`, `agentic_shadow`, `agentic_enforced`
- New CLI:
  - `run-agentic`, `planner-step`, `eval-suite`, `kb-ingest`, `kb-query`
- Config schema expanded:
  - `ai.*`, `policy.*`, `knowledge.*`
  - default policy file: `configs/policy/default_policy.yaml`
- Campaign summary upgraded to `schema_version: 6`:
  - `agentic` metrics + `decision_trace`
- Added unit tests for:
  - agentic policy validation
  - agentic CLI flow
  - knowledge ingest/query roundtrip

## ✅ Additional implementation (Phase 4, 2026-03-06)
- Config/runtime hardening:
  - strict mode now requires `config_version: 2`
  - `recovery.*` added to strict schema
  - `ext_offset` added to glitch/safety schema and runtime checks
  - legacy validator now returns friendly errors for malformed versions, bad numeric casts, and non-mapping sections
- Safety/runtime operations:
  - `SafetyController` clamps/validates `ext_offset`
  - run path guarantees hardware disconnect + MLflow cleanup in `finally`
  - queue/soak serial parallel blocking now resolves effective merged config/template mode
- Agentic control hardening:
  - typed policy validation rejects bad values before patch apply
  - per-path metadata added: `validation_stage`, `effect_type_by_path`, `validation_status_by_path`
  - patch apply now distinguishes `live_applied` vs `deferred_applied`
  - decision trace is persisted as JSONL
- Async serial sync-wrapper hardening:
  - background runner thread avoids `Cannot run the event loop while another loop is running`
  - regression test added for `asyncio.run(...)` caller environments
- Plugin manifest safety:
  - duplicate plugin names now fail fast during registry load
- Incremental quality gates aligned with upgraded subsystems:
  - targeted Ruff and mypy checks now cover agentic/config/safety/serial/plugin paths

## ✅ Additional implementation (Phase 5, 2026-03-06)
- CLI monolith reduction:
  - extracted shared CLI support helpers to `src/cli_support.py`
  - extracted agentic campaign loop helpers to `src/cli_agentic.py`
  - extracted parser builders to `src/cli_parser.py`
  - extracted runtime factories to `src/cli_runtime.py`
  - extracted leaf command handlers to `src/cli_commands.py`
  - extracted core campaign execution to `src/cli_execution.py`
  - extracted queue/soak batch flows to `src/cli_batch.py`
  - extracted HIL preflight helpers to `src/cli_preflight.py`
  - preserved `src.cli` compatibility so existing tests/imports continue to work via facade wrappers/re-exports
- Structural impact:
  - `src/cli.py` reduced from ~2514 lines to ~312 lines across the refactor passes
  - `src.cli` now acts primarily as a compatibility facade and command dispatcher
  - parser, runtime factories, core campaign execution, queue/soak orchestration, HIL preflight, RL/KB/report/validation command handlers, config merge, replay/report helpers, runtime fingerprinting, and agentic campaign orchestration moved out
- Validation:
  - CLI-focused regression suite passed after each extraction stage
  - targeted Ruff and targeted mypy for all extracted CLI modules passed
  - full `pytest -q` remained green (`93 passed, 2 skipped`)
