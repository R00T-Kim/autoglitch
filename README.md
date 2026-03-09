# AUTOGLITCH

[English](README.md) | [한국어](README.ko.md)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](#installation)
[![CI](https://github.com/R00T-Kim/autoglitch/actions/workflows/ci.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/ci.yml)
[![CodeQL](https://github.com/R00T-Kim/autoglitch/actions/workflows/codeql.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/codeql.yml)
[![Semgrep](https://github.com/R00T-Kim/autoglitch/actions/workflows/semgrep.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/semgrep.yml)

Software-first autonomous glitching framework for closed-loop fault-injection campaigns.
AUTOGLITCH combines experiment orchestration, Bayesian/RL optimization, hardware execution,
observation/classification, primitive mapping, and reproducibility reporting in one workflow.

**Quick links:** [Highlights](#highlights) · [Quickstart](#quickstart) · [Hardware onboarding](#hardware-onboarding) · [Quality gates](#quality-gates) · [Documentation](#documentation)

> [!IMPORTANT]
> As of **March 9, 2026**, the software quality gates are green:
> `python -m compileall src tests`, `ruff check src tests`, `mypy src`, `pytest -q`.
> The real-hardware RC workflow exists, but **lab evidence is still pending**.
>
> Latest local validation snapshot:
> - `ruff check src tests` ✅
> - `mypy src` ✅
> - `pytest -q` ✅ `127 passed`

> [!NOTE]
> AUTOGLITCH is a **research-grade alpha**. It is already strong as a software framework and
> mock/HIL-prep environment, but this repository does **not** yet claim field-proven HIL results.

## Highlights

- **Closed-loop campaign execution**: optimizer → hardware → observer → classifier → mapper → feedback.
- **Multiple search strategies**: Bayesian optimization, RL path, benchmark comparison, queue/soak flows.
- **Hardware-aware runtime**: transport-agnostic registry, official profiles, local binding store,
  onboarding commands, health diagnostics, binding-level locks.
- **Typed serial first**: preferred `autoglitch.v1` JSONL protocol via `serial-json-hardware`, with
  legacy text bridge fallback via `serial-command-hardware`.
- **External backend baseline**: `chipwhisperer-hardware` is now supported as the first USB backend.
- **Agentic control path**: planner/policy loop, eval-suite, local knowledge ingest/query utilities.
- **Runtime-selectable components**: observer / classifier / mapper can now be selected by plugin manifest name.
- **Reproducibility artifacts**: campaign summary, run manifest, artifact bundle, RL reports,
  eval-suite reports, JSONL trial logs, decision traces.
- **Backend benchmark path**: benchmark runs can now compare **backend × algorithm** cells and emit
  benchmark/comparison reports.
- **Software quality gates aligned with CI**: local commands and GitHub Actions enforce the same
  repo-wide Ruff, mypy, and pytest checks.

## What works today

| Area | Status | Notes |
| --- | --- | --- |
| Core campaign loop | ✅ | `run`, `report`, replay, queue, soak, benchmark |
| Config validation | ✅ | strict mode requires `config_version: 3`; legacy mode still supported |
| Hardware onboarding | ✅ | `detect-hardware`, `setup-hardware`, `doctor-hardware` |
| Serial transport | ✅ | typed `autoglitch.v1` preferred, legacy text fallback maintained |
| ChipWhisperer backend | ✅ | first external USB backend integrated as `chipwhisperer-hardware` |
| RL workflow | ✅ | `train-rl`, `eval-rl`, SB3 facade + lite fallback |
| Agentic workflow | ✅ | `run-agentic`, `planner-step`, `eval-suite`, `kb-ingest`, `kb-query` |
| HIL preflight / RC workflow | ✅ | `hil-preflight`, `validate-hil-rc` software path is implemented |
| Artifact bundle | ✅ | every run can emit a reproducibility bundle under `experiments/results/bundles/` |
| Backend benchmark compare | ✅ | benchmark output now supports backend × algorithm comparison |
| Full software quality gate | ✅ | compileall + Ruff + mypy + pytest all green |
| Real-hardware RC evidence | ⏳ | workflow exists, measurement artifacts still need to be attached |

## Quickstart

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Installed console scripts:
- `autoglitch`
- `autoglitch-mock-bridge`
- `autoglitch-rpi-bridge`

### 5-minute software smoke run

```bash
python -m src.cli validate-config --target stm32f3
python -m src.cli run --target stm32f3 --trials 50
python -m src.cli report
```

This gives you:
- strict config validation,
- a mock-hardware campaign run,
- a saved campaign report under `experiments/results/`.

### Quick RL smoke path

```bash
python -m src.cli train-rl --target stm32f3 --rl-backend sb3 --steps 2000
python -m src.cli eval-rl --target stm32f3 --rl-backend sb3
```

## Hardware onboarding

### Recommended flow for a real device

```bash
python -m src.cli detect-hardware --target stm32f3 --serial-port /dev/ttyUSB0
python -m src.cli setup-hardware --target stm32f3 --serial-port /dev/ttyUSB0 --force
python -m src.cli doctor-hardware --target stm32f3
python -m src.cli hil-preflight --target stm32f3
python -m src.cli run --target stm32f3 --require-preflight --trials 100
```

### ChipWhisperer flow

```bash
python -m src.cli detect-hardware --hardware chipwhisperer-hardware --target stm32f3
python -m src.cli setup-hardware --hardware chipwhisperer-hardware --target stm32f3 --force
python -m src.cli doctor-hardware --hardware chipwhisperer-hardware --target stm32f3
python -m src.cli run \
  --hardware chipwhisperer-hardware \
  --target stm32f3 \
  --serial-port /dev/ttyUSB0 \
  --trials 100
```

`--serial-port` in this mode is used as the **target UART** for the ChipWhisperer-backed run.

After `setup-hardware`, AUTOGLITCH stores the selected binding in:
- `configs/local/hardware.yaml`

The runtime then resolves hardware in this order:
1. explicit CLI override,
2. saved local binding,
3. auto-detect,
4. legacy/mock fallback.

### Device-free serial path (mock bridge)

Terminal A:

```bash
python -m src.tools.mock_glitch_bridge --port-file /tmp/autoglitch_mock_bridge.port
```

Terminal B:

```bash
python -m src.cli detect-hardware --serial-port "$(cat /tmp/autoglitch_mock_bridge.port)"
python -m src.cli setup-hardware --serial-port "$(cat /tmp/autoglitch_mock_bridge.port)" --force
python -m src.cli run --target stm32f3 --trials 20
```

### RC HIL validation workflow

```bash
python -m src.cli validate-hil-rc \
  --target stm32f3 \
  --serial-port /dev/ttyUSB0 \
  --manual-bridge-restart-ok \
  --manual-link-drop-ok
```

`validate-hil-rc` bundles:
- typed onboarding,
- preflight,
- warmup/stability/repro runs,
- soak/resume and queue/binding-guard drills,
- legacy smoke,
- manual recovery confirmations.

For first lab use, read [`docs/REAL_HARDWARE_CHECKLIST.md`](docs/REAL_HARDWARE_CHECKLIST.md) first.

## CLI overview

| Command group | Commands |
| --- | --- |
| Core execution | `run`, `report`, `replay`, `benchmark` |
| Batch operation | `queue-run`, `soak` |
| Validation / safety | `validate-config`, `hil-preflight`, `validate-hil-rc` |
| Hardware | `detect-hardware`, `setup-hardware`, `doctor-hardware` |
| RL | `train-rl`, `eval-rl` |
| Agentic | `run-agentic`, `planner-step`, `eval-suite`, `kb-ingest`, `kb-query` |
| Extensibility | `list-plugins` |

Full CLI help:

```bash
python -m src.cli --help
```

## How AUTOGLITCH works

```text
config/template
   ↓
optimizer (bayesian / rl)
   ↓ suggest()
hardware runtime (mock / typed serial / legacy serial)
   ↓ execute()
observer → classifier → mapper
   ↓
reward + primitive signal + runtime metadata
   ↓
logger / manifest / summary / replayable JSONL
   ↓
next suggestion or campaign termination
```

Key runtime layers:
- `src/cli.py`: compatibility facade + dispatcher
- `src/cli_commands*.py`: focused command handlers (general / RL / agentic)
- `src/hardware/framework.py`: public facade for the refactored hardware framework
- `src/hardware/_framework_*.py`: internal models, adapters, resolution, capability checks, doctor, locks
- `src/orchestrator/`, `src/optimizer/`, `src/runtime/`, `src/safety/`: core execution pipeline
- `src/logging_viz/`: trial log, campaign summary, run manifest, artifact bundle, tracking helpers

## Configuration and compatibility

### Config baseline

- strict mode requires **`config_version: 3`**
- legacy mode still reads `config_version: 1/2/3` and returns friendly error lists
- official hardware profiles live in `configs/hardware_profiles/*.yaml`
- default local binding path is `configs/local/hardware.yaml`

### Example component block

```yaml
components:
  observer: basic-observer
  classifier: rule-classifier
  mapper: primitive-mapper
```

The runtime now instantiates these components from the plugin registry instead of hardcoded classes.
Component manifests are target-validated before execution.

### Example hardware block

```yaml
config_version: 3

hardware:
  mode: mock          # mock | serial | auto
  adapter: auto       # auto | mock-hardware | serial-json-hardware | serial-command-hardware | chipwhisperer-hardware
  transport: auto
  profile: auto
  auto_detect: true
  binding_file: configs/local/hardware.yaml
  profile_dirs: []
  required_capabilities:
    - glitch.execute
  discovery:
    enabled: true
    candidate_ports: []
    port_globs:
      - /dev/ttyUSB*
      - /dev/ttyACM*
    probe_timeout_s: 0.25
  serial:
    io_mode: async
    keep_open: true
    reconnect_attempts: 2
    reconnect_backoff_s: 0.05
```

### Typed serial protocol

Preferred protocol: **`autoglitch.v1`**

Minimum command set:
- `hello`
- `capabilities`
- `health`
- `execute`
- `reset`
- `trigger`

Legacy text bridge is still supported for compatibility.

## Output artifacts

AUTOGLITCH generates structured artifacts for replay and auditability:

- trial log: `experiments/logs/<run_id>.jsonl`
- campaign summary: `experiments/results/campaign_*_<run_id>.json`
- run manifest: `experiments/results/manifest_<run_id>.json`
- artifact bundle: `experiments/results/bundles/<benchmark_id>/<target>/<backend>/<run_id>/`
- RL train report: `experiments/results/rl_train_*.json`
- RL eval report: `experiments/results/rl_eval_*.json`
- eval-suite report: `experiments/results/eval_suite_*.json`
- benchmark report: `experiments/results/benchmark_*.json`
- comparison report: `experiments/results/comparison_*.json`
- preflight summary: `experiments/results/hil_preflight_*.json`
- RC validation report: `experiments/results/hil_rc_validation_*.json`
- agentic trace: `experiments/results/agentic_trace_*.jsonl`
- knowledge store(default): `data/knowledge/kb.jsonl`

These outputs are backed by typed payload contracts in `src/types.py`.

Campaign summaries now also separate execution health from experiment outcomes:
- `execution_status_breakdown`
- `infra_failure_count`
- `blocked_count`
- `time_to_first_valid_fault`
- `agentic.planner_backend`
- `agentic.advisor_backend`
- `artifact_bundle`
- `bundle_manifest`

## Quality gates

Local development and CI use the same checks:

```bash
python -m compileall src tests
ruff check src tests
mypy src
pytest -q
python -m src.cli validate-config --target stm32f3
```

Serial safety defaults:
- parallel serial execution is blocked unless explicitly enabled,
- binding-level locks fail closed,
- `hil-preflight` + `--require-preflight` is the recommended HIL run path.

## Repository layout

```text
src/
├── cli.py
├── cli_commands.py
├── cli_commands_rl.py
├── cli_commands_agentic.py
├── orchestrator/
├── optimizer/
├── hardware/
├── observer/
├── classifier/
├── mapper/
├── llm_advisor/
├── logging_viz/
├── runtime/
└── safety/
```

Additional project directories:
- `configs/` — target, hardware profile, and policy configuration
- `tests/` — unit and integration tests
- `docs/` — architecture, runbook, safety, roadmap, validation notes
- `experiments/` — generated reports, logs, queue/soak artifacts

## Documentation

| Document | Purpose |
| --- | --- |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | operational command flow and artifact map |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | module boundaries and runtime design |
| [`docs/BENCHMARK_SCHEMA.md`](docs/BENCHMARK_SCHEMA.md) | benchmark task/metric schema |
| [`docs/ARTIFACT_BUNDLE_SCHEMA.md`](docs/ARTIFACT_BUNDLE_SCHEMA.md) | reproducibility bundle schema |
| [`docs/CHIPWHISPERER_ADAPTER_PLAN.md`](docs/CHIPWHISPERER_ADAPTER_PLAN.md) | ChipWhisperer backend scope/status |
| [`docs/RESEARCH_POSITIONING.md`](docs/RESEARCH_POSITIONING.md) | research positioning and differentiation |
| [`docs/SAFETY.md`](docs/SAFETY.md) | safety policy and fail-closed behavior |
| [`docs/PLUGIN_SDK.md`](docs/PLUGIN_SDK.md) | plugin manifest and extension model |
| [`docs/PLAN_IMPLEMENTATION_STATUS.md`](docs/PLAN_IMPLEMENTATION_STATUS.md) | what has already been implemented |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | next milestones and remaining research work |
| [`docs/SOFTWARE_EVOLUTION_2026.md`](docs/SOFTWARE_EVOLUTION_2026.md) | software-upgrade rationale and next ROI items |
| [`docs/HIL_VALIDATION_REPORT_2026Q1.md`](docs/HIL_VALIDATION_REPORT_2026Q1.md) | HIL RC workflow status and evidence tracker |
| [`docs/REAL_HARDWARE_CHECKLIST.md`](docs/REAL_HARDWARE_CHECKLIST.md) | first-lab-use checklist |

## Development

Useful local commands:

```bash
pytest tests/unit -q
ruff format src tests
python -m src.cli list-plugins
python -m src.cli benchmark --help
```

If you change runtime behavior, add or update:
- a regression test,
- the relevant docs under `docs/`,
- schema/report compatibility if artifact shape changes.

## Contributing

Contributions are welcome, but please keep changes aligned with the current repo standards:
- Python 3.10+
- explicit type hints on public interfaces
- repo-wide Ruff + mypy + pytest green before review
- mock hardware in unit tests; reserve device workflows for integration/manual validation

## License

MIT
