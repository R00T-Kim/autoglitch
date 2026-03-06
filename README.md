# AUTOGLITCH

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](#설치)
[![CI](https://github.com/R00T-Kim/autoglitch/actions/workflows/ci.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/ci.yml)
[![CodeQL](https://github.com/R00T-Kim/autoglitch/actions/workflows/codeql.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/codeql.yml)
[![Semgrep](https://github.com/R00T-Kim/autoglitch/actions/workflows/semgrep.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/semgrep.yml)
[![Mode](https://img.shields.io/badge/Hardware-mock%20%7C%20serial-orange)](#실장비-hil-실행)

AUTOGLITCH는 fault injection 실험을 자동화하는 closed-loop 프레임워크입니다.  
파라미터 탐색(BO/RL), 실험 실행, 관측/분류, primitive 매핑, 재현성 리포트를 한 흐름으로 제공합니다.

## 이 프로젝트로 할 수 있는 것
- glitch campaign 실행 및 결과 리포트 생성
- mock/serial 하드웨어 경로 모두 검증
- RL 기반 학습/평가 및 체크포인트 관리
- planner/policy 기반 agentic 제어 루프 실행
- soak/queue 기반 장시간 배치 운영
- HIL preflight로 serial 타깃 안정성 사전 점검
- JSONL trial log / decision trace / campaign summary 기반 재현성 분석

## 처음 시작하는 순서
1. **설치**
2. **설정 검증** (`validate-config`)
3. **mock 캠페인 1회 실행**
4. **report 확인**
5. 필요하면 **mock serial bridge** 로 serial 경로 검증
6. 실장비에서는 **`hil-preflight` 후 run/soak/queue** 순서로 진행

## 설치
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 빠른 시작
```bash
python -m src.cli validate-config --target stm32f3
python -m src.cli run --target stm32f3 --trials 100
python -m src.cli report
```

현재 소프트웨어 검증 상태(2026-03-06):
- `pytest -q` → `93 passed, 2 skipped`
- strict/legacy config regression, agentic trace, async serial running-loop regression 포함

## mock serial / 실장비 실행
장비 없이 serial 코드 경로를 먼저 검증하려면 mock bridge를 사용할 수 있고,
실장비에서는 `hil-preflight` 후 실행하는 흐름을 권장합니다.

```bash
# mock serial path
python -m src.tools.mock_glitch_bridge --port-file /tmp/autoglitch_mock_bridge.port
python -m src.cli run --hardware serial --serial-port "$(cat /tmp/autoglitch_mock_bridge.port)" --trials 20

# real HIL path
python -m src.cli hil-preflight --target stm32f3 --hardware serial --serial-port /dev/ttyUSB0
python -m src.cli run --hardware serial --serial-port /dev/ttyUSB0 --require-preflight --trials 100
```

> `serial` 타깃 병렬 실행은 기본 차단됩니다. 필요한 경우에만 `--allow-parallel-serial`을 명시하세요.

## 자주 쓰는 명령
- `run`: 단일 캠페인 실행
- `report`: 최근 캠페인 리포트 출력
- `hil-preflight`: serial HIL 사전 안정성 점검
- `soak`: 장시간 배치 실행 + 체크포인트/재개
- `queue-run`: 다중 job 실행 (`priority`, `enabled`, 체크포인트/재개)
- `train-rl`, `eval-rl`: RL 백엔드 학습/평가
- `run-agentic`: agentic planner/policy 루프 실행

고급 운영 예시(`soak`, `queue-run`, RL, agentic, replay, benchmark)는 [`docs/RUNBOOK.md`](docs/RUNBOOK.md)를 참고하세요.

## 설정 버전 / 호환성
- strict 모드는 **`config_version: 2`** 를 요구합니다.
- legacy 모드는 구설정 마이그레이션 확인용이며 malformed 입력도 **에러 리스트 반환**을 목표로 합니다.
- `ext_offset`, `recovery.*`, agentic policy metadata는 v2 기준입니다.

### 성능 튜닝 예시 (config)
```yaml
ai:
  mode: agentic_shadow
  planner_interval_trials: 50
  max_patch_delta: 0.5
  max_actions_per_cycle: 3
  confidence_threshold: 0.25

policy:
  allowed_fields:
    - optimizer.bo.candidate_pool_size
    - optimizer.bo.objective_mode
    - optimizer.bo.multi_objective_weights.*

optimizer:
  bo:
    backend: turbo   # auto|heuristic|botorch|turbo|qnehvi
    objective_mode: multi
    multi_objective_weights:
      reward: 1.0
      exploration: 0.5
    candidate_pool_size: 192
    vectorized_heuristic: true
  rl:
    backend: sb3
    warmup_steps: 256
    eval_interval: 1000
    save_best_only: false
    checkpoint_dir: experiments/results

hardware:
  serial:
    io_mode: async
    keep_open: true
    reconnect_attempts: 2
    reconnect_backoff_s: 0.05
    preflight:
      enabled: true
      probe_trials: 30
      max_timeout_rate: 0.05
      max_reset_rate: 0.10
      max_p95_latency_s: 0.50
```

## 리포트에서 먼저 볼 것
- `runtime.throughput_trials_per_second`
- `latency.mean_seconds / p95_seconds / max_seconds`
- `pareto_front`
- `reproducibility.config_hash_sha256 / git_sha / python_version`
- `objective_summary.mode / multi_objective_weights`
- `agentic.mode / event_count / policy_reject_count`
- `decision_trace`
- `training.optimizer_backend / observed_steps`
- `optimizer_runtime`

## 최근 업데이트 (2026-03-06)
- Async serial persistent/reconnect 상태머신 도입
- 이미 실행 중인 event loop 안에서도 동작하는 async serial sync-wrapper 적용
- BO heuristic 벡터화 평가 + 런타임 telemetry 추가
- BO backend 확장(`turbo`, `qnehvi`) + objective mode(`single|multi`)
- RL `train-rl`/`eval-rl` 명령 및 checkpoint/eval 경로 추가
- Agentic Planner/Policy 루프(`off|advisor|agentic_shadow|agentic_enforced`) 추가
- Agentic typed policy 검증 + live/next_run patch metadata + JSONL decision trace 추가
- `run-agentic`, `planner-step`, `eval-suite`, `kb-ingest`, `kb-query` 추가
- 캠페인 요약 `schema_version: 6` 업그레이드
- `hil-preflight` 커맨드 + `--require-preflight` 게이트 도입
- strict config `config_version: 2` + `recovery`/`ext_offset` schema/safety 검증 추가
- run/queue/soak cleanup 및 serial 병렬 차단 로직 강화
- CI는 broad smoke + upgraded subsystem incremental gates로 정렬
- CLI는 facade/dispatch + parser/runtime/execution/batch/preflight/helper 계층으로 분리됨
- 상세 내역: [`docs/PLAN_IMPLEMENTATION_STATUS.md`](docs/PLAN_IMPLEMENTATION_STATUS.md)

## 프로젝트 구조
- `src/`: orchestrator, optimizer, hardware, runtime, safety, CLI
- `configs/`: 기본/타깃 설정
- `experiments/configs/`: repro/soak/queue 템플릿
- `experiments/logs`, `experiments/results`: 실행 산출물
- `tests/`: unit/integration 테스트
- `docs/`: 운영/설계 문서

## 아키텍처 개요
```mermaid
flowchart LR
  A[Optimizer BO/RL] --> B[Orchestrator]
  B --> C[Safety Controller]
  C --> D[Recovery Executor]
  D --> E[Hardware Mock/Serial]
  E --> F[Observer]
  F --> G[Classifier]
  G --> H[Primitive Mapper]
  H --> I[Experiment Logger]
  H --> A
  B --> J[LLM Advisor Optional]
```

상세 설명: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## 라즈베리파이 GPIO 브리지
```bash
python -m src.tools.rpi_glitch_bridge \
  --control-port /dev/ttyUSB0 \
  --glitch-pin 18 --reset-pin 23 --trigger-out-pin 24 --active-high
```

## 품질 확인
```bash
python -m compileall src tests
ruff check src tests --select E,F --ignore E501
ruff check --select E,F,I,SIM --ignore E501 \
  src/agentic \
  src/cli_agentic.py \
  src/cli_batch.py \
  src/cli_commands.py \
  src/cli_execution.py \
  src/cli_parser.py \
  src/cli_preflight.py \
  src/cli_runtime.py \
  src/cli_support.py \
  src/config/schema.py \
  src/config/validator.py \
  src/safety/controller.py \
  src/hardware/serial_async_hardware.py \
  src/hardware/serial_hardware.py \
  src/plugins/registry.py \
  src/types.py \
  tests/unit/test_agentic_policy.py \
  tests/unit/test_agentic_trace.py \
  tests/unit/test_cli_agentic.py \
  tests/unit/test_cli_advanced_modes.py \
  tests/unit/test_cli_helpers.py \
  tests/unit/test_cli_preflight.py \
  tests/unit/test_cli_rl_commands.py \
  tests/unit/test_rl_backends.py \
  tests/unit/test_config_schema.py \
  tests/unit/test_plugin_registry.py \
  tests/unit/test_safety_controller.py \
  tests/unit/test_serial_async_hardware.py
python -m mypy --follow-imports=silent \
  src/cli_agentic.py \
  src/cli_batch.py \
  src/cli_commands.py \
  src/cli_execution.py \
  src/cli_parser.py \
  src/cli_preflight.py \
  src/cli_runtime.py \
  src/cli_support.py \
  src/agentic/patcher.py \
  src/agentic/planner.py \
  src/agentic/policy.py \
  src/agentic/trace.py \
  src/config/schema.py \
  src/config/validator.py \
  src/safety/controller.py \
  src/hardware/serial_async_hardware.py \
  src/hardware/serial_hardware.py \
  src/plugins/registry.py \
  src/types.py
pytest -q
```

## 문서
- `docs/RUNBOOK.md`
- `docs/SAFETY.md`
- `docs/PLUGIN_SDK.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/PLAN_IMPLEMENTATION_STATUS.md`
- `docs/HIL_VALIDATION_REPORT_2026Q1.md`
