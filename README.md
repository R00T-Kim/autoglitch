# AUTOGLITCH

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](#설치)
[![CI](https://github.com/R00T-Kim/autoglitch/actions/workflows/ci.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/ci.yml)
[![CodeQL](https://github.com/R00T-Kim/autoglitch/actions/workflows/codeql.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/codeql.yml)
[![Semgrep](https://github.com/R00T-Kim/autoglitch/actions/workflows/semgrep.yml/badge.svg)](https://github.com/R00T-Kim/autoglitch/actions/workflows/semgrep.yml)

AUTOGLITCH는 fault injection 실험을 자동화하는 closed-loop 프레임워크입니다.
BO/RL 기반 파라미터 탐색, 하드웨어 실행, 관측/분류, primitive 매핑, 재현성 리포트를 한 흐름으로 제공합니다.

## 지금 달라진 점
- strict config 기준선이 **`config_version: 3`** 으로 올라갔습니다.
- 하드웨어 계층이 **transport-agnostic registry + profile + local binding** 구조로 바뀌었습니다.
- 새 하드웨어 명령이 추가되었습니다:
  - `detect-hardware`
  - `setup-hardware`
  - `doctor-hardware`
- serial 경로는 2개를 지원합니다:
  - **`autoglitch.v1` typed JSONL protocol** (`serial-json-hardware`)
  - **legacy text protocol** (`serial-command-hardware`)
- 로컬 장비 바인딩은 기본적으로 **`configs/local/hardware.yaml`** 에 저장됩니다.

현재 소프트웨어 검증 상태(2026-03-06):
- `pytest -q` → **`105 passed, 3 skipped`**
- typed serial adapter / hardware detection / local binding / CLI hardware onboarding 경로 포함

## 설치
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 5분 시작
```bash
python -m src.cli validate-config --target stm32f3
python -m src.cli run --target stm32f3 --trials 100
python -m src.cli report
```

## 지원 하드웨어 온보딩
### 1) 감지
```bash
python -m src.cli detect-hardware --target stm32f3 --serial-port /dev/ttyUSB0
```

### 2) 로컬 바인딩 저장
```bash
python -m src.cli setup-hardware --target stm32f3 --serial-port /dev/ttyUSB0 --force
```

### 3) 상태 진단
```bash
python -m src.cli doctor-hardware --target stm32f3
```

### 4) preflight + 실행
```bash
python -m src.cli hil-preflight --target stm32f3
python -m src.cli run --target stm32f3 --require-preflight --trials 100
```

> `setup-hardware` 이후에는 `run/soak/queue-run/hil-preflight` 가 기본적으로 로컬 바인딩을 사용합니다.

## 장비 없이 serial 경로 확인
```bash
python -m src.tools.mock_glitch_bridge --port-file /tmp/autoglitch_mock_bridge.port
python -m src.cli detect-hardware --serial-port "$(cat /tmp/autoglitch_mock_bridge.port)"
python -m src.cli setup-hardware --serial-port "$(cat /tmp/autoglitch_mock_bridge.port)" --force
python -m src.cli run --target stm32f3 --trials 20
```

## 실장비 운영 기본 순서
1. `validate-config`
2. `detect-hardware`
3. `setup-hardware`
4. `doctor-hardware`
5. `hil-preflight`
6. `run` / `soak` / `queue-run`

## 자주 쓰는 명령
- `run`: 단일 캠페인 실행
- `report`: 최근 캠페인 리포트 출력
- `detect-hardware`: 지원 장비 감지
- `setup-hardware`: 로컬 하드웨어 바인딩 생성/갱신
- `doctor-hardware`: 로컬 바인딩/감지/헬스 진단
- `hil-preflight`: serial HIL 사전 안정성 점검
- `soak`: 장시간 배치 실행 + 체크포인트/재개
- `queue-run`: 다중 job 실행
- `train-rl`, `eval-rl`: RL 백엔드 학습/평가
- `run-agentic`: planner/policy 루프 실행

## 설정 버전 / 호환성
- strict 모드는 **`config_version: 3`** 을 요구합니다.
- `hardware.binding_file` 기본값은 `configs/local/hardware.yaml` 입니다.
- 공식 프로파일은 `configs/hardware_profiles/*.yaml` 에 있습니다.
- legacy validator는 `config_version: 1/2/3` 입력을 읽고 **에러 리스트 반환**을 목표로 합니다.
- legacy serial text protocol은 계속 지원하지만, 신규 권장 경로는 typed serial(`autoglitch.v1`) 입니다.

### 하드웨어 관련 주요 설정
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

## typed serial protocol
공식 serial bridge는 line-delimited JSON 기반 **`autoglitch.v1`** 프로토콜을 사용할 수 있습니다.
최소 명령 세트:
- `hello`
- `capabilities`
- `health`
- `execute`
- `reset`
- `trigger`

legacy bridge는 기존 `GLITCH width=... offset=...` 텍스트 프로토콜로 계속 동작합니다.

## 병렬 실행 주의
- serial 타깃 병렬 실행은 기본 차단됩니다.
- 필요할 때만 `--allow-parallel-serial` 로 해제하세요.
- 같은 로컬 바인딩/장비를 동시에 잡으려 하면 binding-level lock으로 fail-closed 됩니다.
- 장시간 운영 전 `hil-preflight` 와 `--require-preflight` 조합을 권장합니다.

## 품질 확인
```bash
python -m compileall src tests
ruff check src/hardware/framework.py src/hardware/typed_serial_hardware.py src/cli_hardware.py --select E,F,I,SIM,B --ignore E501
python -m mypy --follow-imports=silent \
  src/hardware/framework.py \
  src/hardware/typed_serial_hardware.py \
  src/hardware/serial_hardware.py \
  src/cli_runtime.py \
  src/cli_hardware.py \
  src/cli_preflight.py \
  src/cli_support.py \
  src/tools/mock_glitch_bridge.py \
  src/tools/rpi_glitch_bridge.py
pytest -q
```

## 문서
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/SAFETY.md`](docs/SAFETY.md)
- [`docs/PLUGIN_SDK.md`](docs/PLUGIN_SDK.md)
- [`docs/PLAN_IMPLEMENTATION_STATUS.md`](docs/PLAN_IMPLEMENTATION_STATUS.md)
- [`docs/HIL_VALIDATION_REPORT_2026Q1.md`](docs/HIL_VALIDATION_REPORT_2026Q1.md)
