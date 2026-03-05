# AUTOGLITCH Runbook

## 1) 사전 검증
```bash
python -m src.cli validate-config --config configs/default.yaml --target stm32f3
python -m src.cli list-plugins

# strict schema(기본) / legacy validator 비교
python -m src.cli validate-config --target stm32f3 --config-mode strict
python -m src.cli validate-config --target stm32f3 --config-mode legacy
```

## 1.5) 소프트웨어 전용 serial 에뮬레이션 (장비 없이)
터미널 A:
```bash
python -m src.tools.mock_glitch_bridge --port-file /tmp/autoglitch_mock_bridge.port
```

터미널 B:
```bash
python -m src.cli run \
  --target stm32f3 \
  --hardware serial \
  --serial-io async \
  --serial-port "$(cat /tmp/autoglitch_mock_bridge.port)" \
  --trials 20
```

## 1.6) 라즈베리파이 GPIO 브리지 (실장비 제어)
RPi에서:
```bash
python -m src.tools.rpi_glitch_bridge \
  --control-port /dev/ttyUSB0 \
  --glitch-pin 18 \
  --reset-pin 23 \
  --trigger-out-pin 24 \
  --active-high
```

호스트에서:
```bash
python -m src.cli run \
  --template experiments/configs/soak_hil_stm32f3.yaml \
  --hardware serial \
  --serial-port /dev/ttyUSB0 \
  --trials 50
```

## 2) 기본 실행 (mock)
```bash
python -m src.cli run --target stm32f3 --trials 200
```

## 3) 재현성 캠페인
```bash
python -m src.cli run --template experiments/configs/repro_stm32f3.yaml
python -m src.cli run --template experiments/configs/repro_esp32.yaml
```

## 4) 실장비 단일 실행 (serial)
```bash
python -m src.cli run \
  --template experiments/configs/soak_hil_stm32f3.yaml \
  --hardware serial \
  --serial-port /dev/ttyUSB0 \
  --trials 300
```

## 5) 실장비 soak 모드
```bash
python -m src.cli soak \
  --template experiments/configs/soak_hil_stm32f3.yaml \
  --hardware serial \
  --serial-port /dev/ttyUSB0 \
  --duration-minutes 120 \
  --batch-trials 200

# 중단 후 재개
python -m src.cli soak \
  --template experiments/configs/soak_hil_stm32f3.yaml \
  --hardware serial \
  --serial-port /dev/ttyUSB0 \
  --batch-trials 200 \
  --max-batches 20 \
  --resume

# 배치 실패 시에도 다음 배치 지속
python -m src.cli soak \
  --template experiments/configs/soak_hil_stm32f3.yaml \
  --batch-trials 200 \
  --max-batches 20 \
  --continue-on-error

# mock 환경에서 배치 병렬 실행 + 디스패치 간격(rate-limit)
python -m src.cli soak \
  --target stm32f3 \
  --hardware mock \
  --batch-trials 200 \
  --max-batches 20 \
  --max-workers 2 \
  --batch-interval-s 0.5 \
  --continue-on-error
```

## 6) 큐 기반 다중 작업 실행
```bash
python -m src.cli queue-run --queue experiments/configs/queue_hil.yaml
# 중단 후 재개
python -m src.cli queue-run \
  --queue experiments/configs/queue_hil.yaml \
  --resume \
  --checkpoint-file experiments/results/queue_checkpoint_hil.json

# mock 타깃 병렬 워커 실행
python -m src.cli queue-run \
  --queue experiments/configs/queue_hil.yaml \
  --max-workers 2 \
  --continue-on-error
```

큐 job은 `priority`(높을수록 먼저 실행), `enabled` 필드를 지원한다.
```yaml
jobs:
  - name: stm32f3_high
    priority: 100
    enabled: true
    template: experiments/configs/soak_hil_stm32f3.yaml
```

> `hardware: serial` 환경에서 병렬 워커는 기본 차단된다.
> 필요 시 `--allow-parallel-serial`을 명시해 수동으로 해제한다.

## 7) BO vs RL-lite 비교
```bash
python -m src.cli benchmark \
  --template experiments/configs/repro_stm32f3.yaml \
  --algorithms bayesian,rl \
  --rl-backend sb3 \
  --runs 5 \
  --trials 200
```

## 8) 로그 재생/검증
```bash
python -m src.cli replay \
  --log experiments/logs/<run_id>.jsonl \
  --report experiments/results/<campaign_report>.json
```

## 출력 산출물
- Trial log: `experiments/logs/<run_id>.jsonl`
- Campaign summary: `experiments/results/campaign_*_<run_id>.json`
- Run manifest: `experiments/results/manifest_<run_id>.json`
- Repro aggregate: `experiments/results/repro_*.json`
- Benchmark comparison: `experiments/results/comparison_*.json`
- Queue summary: `experiments/results/queue_*.json`
- Soak summary: `experiments/results/soak_*.json`
