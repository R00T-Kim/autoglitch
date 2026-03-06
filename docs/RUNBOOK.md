# AUTOGLITCH Runbook

## 1) 사전 검증
```bash
python -m src.cli validate-config --config configs/default.yaml --target stm32f3
python -m src.cli list-plugins
python -m src.cli validate-config --target stm32f3 --config-mode strict
python -m src.cli validate-config --target stm32f3 --config-mode legacy
```

- strict 기준선은 **`config_version: 3`** 이다.
- legacy validator는 `config_version: 1/2/3` 입력을 읽고 에러 리스트를 반환한다.
- 공식 하드웨어 프로파일은 `configs/hardware_profiles/*.yaml` 에 있다.

## 2) 하드웨어 온보딩 (권장 시작점)
### 감지
```bash
python -m src.cli detect-hardware --target stm32f3 --serial-port /dev/ttyUSB0
```

### 로컬 바인딩 생성
```bash
python -m src.cli setup-hardware --target stm32f3 --serial-port /dev/ttyUSB0 --force
```

### 진단
```bash
python -m src.cli doctor-hardware --target stm32f3
```

기본 로컬 바인딩 파일:
- `configs/local/hardware.yaml`

실행 경로(`run`, `soak`, `queue-run`, `hil-preflight`)는 하드웨어 인자를 주지 않으면 이 로컬 바인딩을 우선 사용한다.
- `hardware.required_capabilities`를 설정하면 감지/해결 단계에서 capability 부족 장비를 자동 제외한다.

## 3) 장비 없이 serial 에뮬레이션
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

## 4) 기본 실행
### mock
```bash
python -m src.cli run --target stm32f3 --trials 200
```

### HIL preflight
```bash
python -m src.cli hil-preflight --target stm32f3

# 임계값 override
python -m src.cli hil-preflight \
  --target stm32f3 \
  --probe-trials 50 \
  --max-timeout-rate 0.03 \
  --max-reset-rate 0.08 \
  --max-p95-latency-s 0.4
```

### 실장비 단일 실행
```bash
python -m src.cli run --target stm32f3 --require-preflight --trials 300
```

### RC 최종 검증 워크플로우
```bash
python -m src.cli validate-hil-rc \
  --target stm32f3 \
  --serial-port /dev/ttyUSB0 \
  --manual-bridge-restart-ok \
  --manual-link-drop-ok
```

- 기본 경로는 typed serial(`autoglitch.v1`)이며, legacy text serial은 smoke만 수행한다.
- 이 명령은 software gate, typed onboarding, preflight, warmup/stability/repro, soak/resume, queue/binding guard, legacy smoke를 하나의 RC report로 묶는다.
- bridge 재시작/링크 드롭 같은 recovery drill은 자동 검증이 아니므로, 실험자가 실제 수행 후 confirmation flag로 승인해야 한다.

## 5) soak / queue
### soak
```bash
python -m src.cli soak \
  --target stm32f3 \
  --require-preflight \
  --duration-minutes 120 \
  --batch-trials 200

python -m src.cli soak \
  --target stm32f3 \
  --require-preflight \
  --batch-trials 200 \
  --max-batches 20 \
  --resume
```

### queue
```bash
python -m src.cli queue-run --queue experiments/configs/queue_hil.yaml --require-preflight
python -m src.cli queue-run \
  --queue experiments/configs/queue_hil.yaml \
  --require-preflight \
  --resume \
  --checkpoint-file experiments/results/queue_checkpoint_hil.json
```

> serial 하드웨어 병렬 실행은 기본 차단된다. 필요 시 `--allow-parallel-serial` 로 명시 해제한다.
> 동일한 장비 바인딩은 runtime lock으로 한 번에 하나의 실행만 점유한다.

## 6) typed serial vs legacy serial
### 권장: typed serial (`serial-json-hardware`)
- 프로토콜: `autoglitch.v1`
- 명령: `hello`, `capabilities`, `health`, `execute`, `reset`, `trigger`
- `detect-hardware` / `setup-hardware` 자동 감지 우선 대상

### 호환: legacy serial (`serial-command-hardware`)
- 프로토콜: `GLITCH width=... offset=... voltage=... repeat=... ext_offset=...`
- 수동으로 강제하려면:
```bash
python -m src.cli run --hardware serial --serial-port /dev/ttyUSB0 --trials 50
```

## 7) 라즈베리파이 GPIO 브리지
RPi에서:
```bash
python -m src.tools.rpi_glitch_bridge \
  --control-port /dev/ttyUSB0 \
  --glitch-pin 18 \
  --reset-pin 23 \
  --trigger-out-pin 24 \
  --active-high
```

이 브리지는 legacy text protocol과 typed JSONL protocol 둘 다 처리할 수 있다.

## 8) RL / Agentic / Replay
### RL
```bash
python -m src.cli train-rl --target stm32f3 --rl-backend sb3 --steps 5000 --run-tag rl_baseline
python -m src.cli eval-rl --target stm32f3 --rl-backend sb3 --checkpoint experiments/results/rl_checkpoint.json
```

### Agentic
```bash
python -m src.cli run-agentic \
  --template experiments/configs/repro_stm32f3.yaml \
  --ai-mode agentic_enforced \
  --policy-file configs/policy/default_policy.yaml
```

### Replay
```bash
python -m src.cli replay \
  --log experiments/logs/<run_id>.jsonl \
  --report experiments/results/<campaign_report>.json
```

## 9) 운영 산출물
- Trial log: `experiments/logs/<run_id>.jsonl`
- Campaign summary: `experiments/results/campaign_*_<run_id>.json`
- Run manifest: `experiments/results/manifest_<run_id>.json`
- Queue summary: `experiments/results/queue_*.json`
- Soak summary: `experiments/results/soak_*.json`
- HIL preflight summary: `experiments/results/hil_preflight_*.json`
- RC HIL validation summary: `experiments/results/hil_rc_validation_*.json`
- Agentic trace: `experiments/results/agentic_trace_*.jsonl`

## 10) 권장 체크리스트
1. `validate-config`
2. `detect-hardware`
3. `setup-hardware`
4. `doctor-hardware`
5. `hil-preflight`
6. `validate-hil-rc`
7. `run` / `soak` / `queue-run`
8. 결과는 summary + manifest + trace까지 함께 보관
