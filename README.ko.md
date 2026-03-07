# AUTOGLITCH

[English](README.md) | [한국어](README.ko.md)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](#설치)
[![CI](https://github.com/R00T-Kim/autoglitch/actions/workflows/ci.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/ci.yml)
[![CodeQL](https://github.com/R00T-Kim/autoglitch/actions/workflows/codeql.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/codeql.yml)
[![Semgrep](https://github.com/R00T-Kim/autoglitch/actions/workflows/semgrep.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/semgrep.yml)

폐쇄 루프(closed-loop) fault injection 캠페인을 위한 소프트웨어 중심 자율 글리칭 프레임워크입니다.
AUTOGLITCH는 실험 오케스트레이션, Bayesian/RL 최적화, 하드웨어 실행, 관측/분류,
primitive 매핑, 재현성 리포팅을 하나의 워크플로우로 묶습니다.

**바로가기:** [핵심 특징](#핵심-특징) · [빠른 시작](#빠른-시작) · [하드웨어 온보딩](#하드웨어-온보딩) · [품질 게이트](#품질-게이트) · [문서](#문서)

> [!IMPORTANT]
> **2026년 3월 7일 기준**, 소프트웨어 품질 게이트는 모두 green 상태입니다.
> `python -m compileall src tests`, `ruff check src tests`, `mypy src`, `pytest -q`
> 는 전부 통과합니다.
> 다만 **실장비 RC 증거는 아직 수집 중**입니다.
>
> 최신 로컬 검증 스냅샷:
> - `ruff check src tests` ✅
> - `mypy src` ✅
> - `pytest -q` ✅ `113 passed, 3 skipped`

> [!NOTE]
> AUTOGLITCH는 **연구용 알파(research-grade alpha)** 입니다.
> 소프트웨어 프레임워크와 mock/HIL 준비 환경으로서는 꽤 강하지만,
> 아직 실장비 현장 검증이 끝난 프로젝트라고 주장하진 않습니다.

## 핵심 특징

- **폐쇄 루프 캠페인 실행**: optimizer → hardware → observer → classifier → mapper → feedback.
- **다양한 탐색 전략**: Bayesian optimization, RL 경로, benchmark 비교, queue/soak 플로우.
- **하드웨어 인지 런타임**: transport-agnostic registry, 공식 profile, local binding store,
  온보딩 명령, health 진단, binding-level lock.
- **typed serial 우선 경로**: `serial-json-hardware`를 통한 `autoglitch.v1` JSONL 프로토콜을 권장하고,
  `serial-command-hardware` legacy text bridge도 유지합니다.
- **agentic 제어 경로**: planner/policy 루프, eval-suite, 로컬 knowledge ingest/query 유틸리티.
- **재현성 산출물**: campaign summary, run manifest, RL report, eval-suite report,
  JSONL trial log, decision trace.
- **CI와 같은 품질 게이트**: 로컬 개발 명령과 GitHub Actions가 동일한 repo-wide
  Ruff, mypy, pytest 기준을 사용합니다.

## 지금 되는 것

| 영역 | 상태 | 설명 |
| --- | --- | --- |
| 코어 캠페인 루프 | ✅ | `run`, `report`, `replay`, `queue`, `soak`, `benchmark` |
| 설정 검증 | ✅ | strict mode는 `config_version: 3` 요구, legacy mode도 지원 |
| 하드웨어 온보딩 | ✅ | `detect-hardware`, `setup-hardware`, `doctor-hardware` |
| serial transport | ✅ | typed `autoglitch.v1` 권장, legacy text fallback 유지 |
| RL 워크플로우 | ✅ | `train-rl`, `eval-rl`, SB3 facade + lite fallback |
| agentic 워크플로우 | ✅ | `run-agentic`, `planner-step`, `eval-suite`, `kb-ingest`, `kb-query` |
| HIL preflight / RC 워크플로우 | ✅ | `hil-preflight`, `validate-hil-rc` 소프트웨어 경로 구현됨 |
| 전체 소프트웨어 품질 게이트 | ✅ | compileall + Ruff + mypy + pytest 전부 green |
| 실장비 RC 증거 | ⏳ | 워크플로우는 있으나 측정 artifact는 아직 필요 |

## 빠른 시작

### 설치

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

설치되는 콘솔 스크립트:
- `autoglitch`
- `autoglitch-mock-bridge`
- `autoglitch-rpi-bridge`

### 5분 소프트웨어 스모크 런

```bash
python -m src.cli validate-config --target stm32f3
python -m src.cli run --target stm32f3 --trials 50
python -m src.cli report
```

이 흐름으로 바로 얻는 것:
- strict config validation,
- mock-hardware 기반 캠페인 실행,
- `experiments/results/` 아래 저장되는 campaign report.

### 빠른 RL 스모크 경로

```bash
python -m src.cli train-rl --target stm32f3 --rl-backend sb3 --steps 2000
python -m src.cli eval-rl --target stm32f3 --rl-backend sb3
```

## 하드웨어 온보딩

### 실장비 권장 흐름

```bash
python -m src.cli detect-hardware --target stm32f3 --serial-port /dev/ttyUSB0
python -m src.cli setup-hardware --target stm32f3 --serial-port /dev/ttyUSB0 --force
python -m src.cli doctor-hardware --target stm32f3
python -m src.cli hil-preflight --target stm32f3
python -m src.cli run --target stm32f3 --require-preflight --trials 100
```

`setup-hardware` 이후 선택된 binding은 아래에 저장됩니다.
- `configs/local/hardware.yaml`

런타임의 하드웨어 해석 순서:
1. CLI 명시 override
2. 저장된 local binding
3. auto-detect
4. legacy/mock fallback

### 장비 없는 serial 경로 (mock bridge)

터미널 A:

```bash
python -m src.tools.mock_glitch_bridge --port-file /tmp/autoglitch_mock_bridge.port
```

터미널 B:

```bash
python -m src.cli detect-hardware --serial-port "$(cat /tmp/autoglitch_mock_bridge.port)"
python -m src.cli setup-hardware --serial-port "$(cat /tmp/autoglitch_mock_bridge.port)" --force
python -m src.cli run --target stm32f3 --trials 20
```

### RC HIL 검증 워크플로우

```bash
python -m src.cli validate-hil-rc \
  --target stm32f3 \
  --serial-port /dev/ttyUSB0 \
  --manual-bridge-restart-ok \
  --manual-link-drop-ok
```

`validate-hil-rc`는 아래를 하나로 묶습니다.
- typed onboarding,
- preflight,
- warmup/stability/repro run,
- soak/resume, queue/binding-guard drill,
- legacy smoke,
- manual recovery confirmation.

실험실에서 처음 장비를 붙일 때는
[`docs/REAL_HARDWARE_CHECKLIST.md`](docs/REAL_HARDWARE_CHECKLIST.md)를 먼저 보세요.

## CLI 개요

| 명령 그룹 | 명령 |
| --- | --- |
| 코어 실행 | `run`, `report`, `replay`, `benchmark` |
| 배치 운용 | `queue-run`, `soak` |
| 검증 / 안전 | `validate-config`, `hil-preflight`, `validate-hil-rc` |
| 하드웨어 | `detect-hardware`, `setup-hardware`, `doctor-hardware` |
| RL | `train-rl`, `eval-rl` |
| agentic | `run-agentic`, `planner-step`, `eval-suite`, `kb-ingest`, `kb-query` |
| 확장성 | `list-plugins` |

전체 CLI 도움말:

```bash
python -m src.cli --help
```

## AUTOGLITCH 동작 방식

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
다음 제안 또는 캠페인 종료
```

주요 런타임 레이어:
- `src/cli.py`: compatibility facade + dispatcher
- `src/cli_commands*.py`: 역할별 command handler (general / RL / agentic)
- `src/hardware/framework.py`: 리팩터링된 하드웨어 프레임워크의 public facade
- `src/hardware/_framework_*.py`: internal models, adapters, resolution, capability checks, doctor, locks
- `src/orchestrator/`, `src/optimizer/`, `src/runtime/`, `src/safety/`: 코어 실행 파이프라인
- `src/logging_viz/`: trial log, campaign summary, run manifest, tracking helper

## 설정과 호환성

### 설정 기준선

- strict mode는 **`config_version: 3`** 를 요구합니다.
- legacy mode는 여전히 `config_version: 1/2/3` 을 읽고 friendly error list를 반환합니다.
- 공식 hardware profile은 `configs/hardware_profiles/*.yaml` 에 있습니다.
- 기본 local binding path는 `configs/local/hardware.yaml` 입니다.

### 예시 hardware 블록

```yaml
config_version: 3

hardware:
  mode: mock          # mock | serial | auto
  adapter: auto       # auto | mock-hardware | serial-json-hardware | serial-command-hardware
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

### typed serial 프로토콜

권장 프로토콜: **`autoglitch.v1`**

최소 명령 세트:
- `hello`
- `capabilities`
- `health`
- `execute`
- `reset`
- `trigger`

호환성을 위해 legacy text bridge도 계속 지원합니다.

## 출력 산출물

AUTOGLITCH는 replay와 auditability를 위해 구조화된 산출물을 생성합니다.

- trial log: `experiments/logs/<run_id>.jsonl`
- campaign summary: `experiments/results/campaign_*_<run_id>.json`
- run manifest: `experiments/results/manifest_<run_id>.json`
- RL train report: `experiments/results/rl_train_*.json`
- RL eval report: `experiments/results/rl_eval_*.json`
- eval-suite report: `experiments/results/eval_suite_*.json`
- preflight summary: `experiments/results/hil_preflight_*.json`
- RC validation report: `experiments/results/hil_rc_validation_*.json`
- agentic trace: `experiments/results/agentic_trace_*.jsonl`
- knowledge store(기본값): `data/knowledge/kb.jsonl`

이 출력물들은 `src/types.py`의 typed payload 계약을 기반으로 생성됩니다.

## 품질 게이트

로컬 개발과 CI는 동일한 검사를 사용합니다.

```bash
python -m compileall src tests
ruff check src tests
mypy src
pytest -q
python -m src.cli validate-config --target stm32f3
```

serial 안전 기본값:
- 병렬 serial 실행은 명시적으로 허용하지 않는 한 차단됩니다.
- binding-level lock은 fail-closed로 동작합니다.
- HIL 실행은 `hil-preflight` + `--require-preflight` 조합이 권장 경로입니다.

## 저장소 구조

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

추가 주요 디렉터리:
- `configs/` — target, hardware profile, policy 설정
- `tests/` — unit / integration 테스트
- `docs/` — architecture, runbook, safety, roadmap, validation notes
- `experiments/` — report, log, queue/soak artifact

## 문서

| 문서 | 용도 |
| --- | --- |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | 운영 명령 흐름과 artifact map |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 모듈 경계와 runtime design |
| [`docs/SAFETY.md`](docs/SAFETY.md) | safety policy와 fail-closed behavior |
| [`docs/PLUGIN_SDK.md`](docs/PLUGIN_SDK.md) | plugin manifest와 extension model |
| [`docs/PLAN_IMPLEMENTATION_STATUS.md`](docs/PLAN_IMPLEMENTATION_STATUS.md) | 이미 구현된 내용 정리 |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | 다음 milestone과 남은 연구 과제 |
| [`docs/SOFTWARE_EVOLUTION_2026.md`](docs/SOFTWARE_EVOLUTION_2026.md) | 소프트웨어 업그레이드 rationale과 다음 ROI 항목 |
| [`docs/HIL_VALIDATION_REPORT_2026Q1.md`](docs/HIL_VALIDATION_REPORT_2026Q1.md) | HIL RC workflow 상태와 evidence tracker |
| [`docs/REAL_HARDWARE_CHECKLIST.md`](docs/REAL_HARDWARE_CHECKLIST.md) | 첫 실험실 투입 체크리스트 |

## 개발

유용한 로컬 명령:

```bash
pytest tests/unit -q
ruff format src tests
python -m src.cli list-plugins
python -m src.cli benchmark --help
```

런타임 동작을 바꾸면 같이 업데이트해야 할 것:
- regression test,
- `docs/` 아래 관련 문서,
- artifact shape가 바뀌는 경우 schema/report compatibility.

## 기여

기여는 환영하지만, 현재 저장소 기준은 맞춰주세요.
- Python 3.10+
- public interface에 explicit type hints
- 리뷰 전 repo-wide Ruff + mypy + pytest green
- unit test에서는 mock hardware 사용, device workflow는 integration/manual validation로 분리

## 라이선스

MIT
