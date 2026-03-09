# Plan Implementation Status (2026-03-09)

## ✅ Latest snapshot (2026-03-09)

- `ruff check src tests` ✅
- `mypy src` ✅
- `pytest -q` ✅ (`127 passed`)

아래의 이전 phase 기록은 **히스토리**이며, 최신 구현 상태는 아래 Phase 10 항목을 우선 본다.

## ✅ Implemented in this cycle (Phase 10, 2026-03-09)

### 1) Backend-aware benchmark
- `benchmark`가 이제 algorithm-only 비교가 아니라 **backend × algorithm** 비교를 수행한다.
- 새 benchmark 메타데이터:
  - `benchmark_id`
  - `benchmark_task`
  - `operator`
  - `board_id`
  - `session_id`
  - `wiring_profile`
  - `board_prep_profile`
  - `power_profile`
- benchmark 결과는:
  - `benchmark_*.json`
  - `comparison_*.json`
  - per-run artifact bundle
  로 저장된다.

### 2) Artifact bundle generator
- 모든 run은 이제 `experiments/results/bundles/...` 아래에 bundle을 생성할 수 있다.
- bundle에는 최소 아래가 포함된다.
  - campaign summary
  - run manifest
  - trial log
  - metadata
  - hardware resolution
  - operator notes
  - optional preflight / RC validation
- bundle completeness:
  - `required_ok`
  - `research_complete`
  - `rc_complete`

### 3) ChipWhisperer backend integration
- `chipwhisperer-hardware` adapter/profile 추가
- detect / setup / doctor / run 경로에 통합
- `hardware.chipwhisperer.*` strict schema 추가
- ChipWhisperer 실행 시 `--serial-port`는 target UART로 전달될 수 있다.

### 4) Result/report schema uplift
- campaign summary는 `schema_version: 8`
- 추가/확장된 핵심 필드:
  - `time_to_first_valid_fault`
  - `artifact_bundle`
  - `bundle_manifest`
  - `component_plugins`
  - `benchmark`
- rerun/benchmark aggregate에도 infra-failure rate, blocked rate, bundle completeness 집계가 포함된다.

## ✅ Implemented in this cycle (Phase 9, 2026-03-08)

### 1) Runtime component plugin wiring
- Added strict config support for:
  - `components.observer`
  - `components.classifier`
  - `components.mapper`
- `run` no longer hardcodes observer / classifier / mapper classes.
- Runtime components are now instantiated from plugin manifests through `PluginRegistry`.
- Target compatibility is validated before the selected component plugin is used.

### 2) Hardware profile override correctness
- Added `build_registry_from_config(...)` so all runtime paths can build a registry with `hardware.profile_dirs`.
- Main hardware creation path now uses the config-aware registry builder.
- Profile loading now allows later profile directories to override official profiles while inheriting unspecified fields.
- Added regression coverage proving custom `profile_dirs` can override typed-serial defaults.

### 3) Infra-failure separation from experiment outcomes
- Added `ExecutionMetadata` to `TrialResult`.
- Orchestrator now records execution state separately from fault classification:
  - `ok`
  - `infra_failure`
  - `blocked`
- Infra failures no longer feed optimizer observations or primitive mapping as normal experimental outcomes.
- Campaign summary schema upgraded to `schema_version: 7` with:
  - `execution_status_breakdown`
  - `infra_failure_count`
  - `blocked_count`

### 4) Backend transparency in summaries
- Campaign summaries now record:
  - `agentic.planner_backend`
  - `agentic.advisor_backend`
- `run` summaries also expose selected component plugin names.

### 5) Validation
- Added/updated tests for:
  - runtime component plugin selection
  - plugin class instantiation
  - strict config parsing for component selection
  - profile-dir hardware override behavior
  - infra-failure isolation in orchestrator recovery flow
  - campaign summary / replay summary schema updates
- Current validation snapshot (2026-03-08):
  - `ruff check src tests` ✅
  - `mypy src` ✅
  - `pytest -q` ✅ (`118 passed, 3 skipped`)

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
- Current test status (2026-03-07): `113 passed, 3 skipped`.

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
  - strict mode now requires `config_version: 3`
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
  - full `pytest -q` remained green (`113 passed, 3 skipped`)


## ✅ Additional implementation (Phase 6, 2026-03-06)
- Hardware framework v1 added:
  - `src/hardware/framework.py` registry/profile/binding resolution
  - official profiles under `configs/hardware_profiles/*.yaml`
  - local binding store default: `configs/local/hardware.yaml`
- New hardware adapters/paths:
  - `serial-json-hardware` typed JSONL adapter (`autoglitch.v1`)
  - legacy `serial-command-hardware` retained as fallback
- New CLI commands:
  - `detect-hardware`
  - `setup-hardware`
  - `doctor-hardware`
- Runtime integration:
  - hardware creation now resolves explicit adapter -> local binding -> auto-detect -> legacy fallback/mock fallback
  - HIL preflight now uses resolved transport rather than only raw `hardware.mode`
- Bridge support:
  - mock bridge now speaks both legacy text and typed JSONL
  - Raspberry Pi bridge now speaks both legacy text and typed JSONL
- Validation:
  - added tests for typed serial adapter, hardware framework resolution, CLI onboarding commands, bridge typed protocol handling
- current test status: `113 passed, 3 skipped`

## ✅ Additional implementation (Phase 7, 2026-03-06)
- RC HIL validation workflow implemented around `validate-hil-rc`:
  - software gate + typed onboarding + preflight + warmup/stability/repro
  - soak/resume + queue/binding guard drill
  - legacy smoke + manual recovery confirmation flags
- `doctor-hardware` now performs adapter healthchecks and degrades on stale local bindings.
- Docs call out that bridge restart / serial link drop drills still require explicit operator confirmation in the lab.
- Current test status updated to `113 passed, 3 skipped`.

## ✅ Additional implementation (Phase 8, 2026-03-07)
- Full-repo quality gate hardening completed:
  - `python -m compileall src tests`
  - `ruff check src tests`
  - `mypy src`
  - `pytest -q`
  - local validation and GitHub CI now use the same gate set
- CLI command cluster split advanced:
  - `src/cli_commands.py` now keeps general report/benchmark/validation/replay handlers
  - `src/cli_commands_rl.py` owns RL train/eval handlers
  - `src/cli_commands_agentic.py` owns planner/eval-suite/knowledge handlers
- Hardware framework internals split behind compatibility facade:
  - `src/hardware/framework.py` → public import surface only
  - `_framework_models`, `_framework_adapters`, `_framework_resolution`,
    `_framework_capabilities`, `_framework_doctor`, `_framework_locks`
- Typed payload contracts expanded in `src/types.py`:
  - campaign summary / run manifest
  - RL train/eval reports
  - eval-suite and knowledge query payloads
- Regression coverage added/kept green for:
  - campaign summary JSONL/report schema path
  - SB3 checkpoint roundtrip / RL backend report flow
- Current validation snapshot (2026-03-07):
  - `python -m compileall src tests` ✅
  - `ruff check src tests` ✅
  - `mypy src` ✅
  - `pytest -q` ✅ (`113 passed, 3 skipped`)
  - `python -m src.cli validate-config --target stm32f3` ✅
