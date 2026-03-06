# AUTOGLITCH 실장비 실행 체크리스트

이 문서는 **실제 장비를 랩에 연결한 뒤 첫 실행부터 RC 검증까지** 순서대로 따라갈 수 있게 만든 운영 체크리스트다.  
공식 권장 경로는 **typed serial (`autoglitch.v1`)** 이며, legacy text serial은 호환성 확인용으로만 사용한다.

## 0) 범위와 목표
- 대상: 대표 실장비 1대 + 대표 타깃 1종
- 목표:
  1. 장비 감지/바인딩 성공
  2. `doctor-hardware` / `hil-preflight` 통과
  3. 첫 실장비 run 성공
  4. 필요 시 `validate-hil-rc` 로 RC 검증 수행

## 1) 사전 준비
### 장비/배선
- [ ] glitch 출력 경로 연결 확인
- [ ] target reset 경로 연결 확인
- [ ] trigger 입력/출력 경로 연결 확인
- [ ] serial 연결 확인 (`/dev/ttyUSB*`, `/dev/ttyACM*` 등)
- [ ] 전원, 공통 GND, polarity(active-high/low) 확인

### 소프트웨어
- [ ] 가상환경 생성 및 활성화
- [ ] `python -m pip install -e ".[dev]"` 완료
- [ ] `python -m src.cli validate-config --target <target>` 통과
- [ ] `pytest -q` 최근 기준 green 확인

## 2) 장비 감지 / 바인딩
### 감지
```bash
python -m src.cli detect-hardware --target stm32f3 --serial-port /dev/ttyUSB0
```

- [ ] typed adapter가 high-confidence match로 식별됨
- [ ] capability 출력에 `glitch.execute`, `target.reset`, `target.trigger`, `healthcheck` 포함

### 로컬 바인딩 저장
```bash
python -m src.cli setup-hardware --target stm32f3 --serial-port /dev/ttyUSB0 --force
```

- [ ] `configs/local/hardware.yaml` 생성 또는 갱신됨
- [ ] 이후 `run`, `soak`, `queue-run`, `hil-preflight` 에서 별도 포트 인자 없이 같은 바인딩을 재사용함

## 3) 상태 진단
```bash
python -m src.cli doctor-hardware --target stm32f3
```

- [ ] 상태가 `ok`
- [ ] stale binding 아님
- [ ] adapter `healthcheck()` 성공
- [ ] 권한/포트 충돌/중복 바인딩 문제 없음

문제 발생 시:
- [ ] 포트 점유 프로세스 확인
- [ ] bridge 재시작
- [ ] 케이블/전원/GND 재확인
- [ ] binding 파일 삭제 후 `setup-hardware --force` 재실행

## 4) Preflight
기본:
```bash
python -m src.cli hil-preflight --target stm32f3
```

강화 임계값 예시:
```bash
python -m src.cli hil-preflight \
  --target stm32f3 \
  --probe-trials 50 \
  --max-timeout-rate 0.03 \
  --max-reset-rate 0.08 \
  --max-p95-latency-s 0.4
```

- [ ] `valid == true`
- [ ] timeout/reset/latency 기준 통과
- [ ] preflight artifact 저장 성공

## 5) 첫 실장비 실행
```bash
python -m src.cli run --target stm32f3 --require-preflight --trials 100
```

- [ ] 프로세스 크래시 없음
- [ ] hardware disconnect/cleanup 정상
- [ ] summary / manifest / log 생성 성공
- [ ] 관측 결과가 의미 있게 수집됨

## 6) 운영성 점검
### binding lock
- [ ] 동일 로컬 바인딩으로 2개 실행을 동시에 시작했을 때 fail-closed 되는지 확인

### queue guard
- [ ] serial job queue를 병렬로 실행했을 때 `--allow-parallel-serial` 없으면 차단되는지 확인

### soak / resume
```bash
python -m src.cli soak \
  --target stm32f3 \
  --require-preflight \
  --duration-minutes 120 \
  --batch-trials 200
```

- [ ] 장시간 실행 중 stuck lock 없음
- [ ] artifact 누락/손상 없음
- [ ] `--resume` 재개 성공

## 7) RC 최종 검증
```bash
python -m src.cli validate-hil-rc \
  --target stm32f3 \
  --serial-port /dev/ttyUSB0 \
  --manual-bridge-restart-ok \
  --manual-link-drop-ok
```

- [ ] software gate 통과
- [ ] typed onboarding / preflight / warmup / stability / repro 통과
- [ ] queue guard / binding lock drill 통과
- [ ] soak / resume drill 통과
- [ ] legacy smoke 최소 호환성 통과
- [ ] `experiments/results/hil_rc_validation_*.json` 생성

## 8) 산출물 보관
- [ ] `experiments/logs/<run_id>.jsonl`
- [ ] `experiments/results/campaign_*_<run_id>.json`
- [ ] `experiments/results/manifest_<run_id>.json`
- [ ] `experiments/results/hil_preflight_*.json`
- [ ] `experiments/results/hil_rc_validation_*.json`
- [ ] 필요 시 `agentic_trace_*.jsonl`, `queue_*.json`, `soak_*.json`

## 9) 실패 시 중단 기준
아래 중 하나라도 나오면 **즉시 중단**:
- [ ] reset/trigger/glitch 경로가 불안정함
- [ ] timeout/reset rate가 반복적으로 임계값 초과
- [ ] binding lock이 해제되지 않음
- [ ] cleanup 누락 또는 포트가 계속 점유됨
- [ ] artifact 생성 실패
- [ ] operator가 배선/전원 안정성을 확신할 수 없음

## 10) 최종 승인 메모
- [ ] 사용 장비:
- [ ] 사용 타깃:
- [ ] 사용 포트:
- [ ] bridge 타입:
- [ ] preflight 결과 파일:
- [ ] 첫 실장비 run 결과 파일:
- [ ] RC validation 결과 파일:
- [ ] 승인 일시:
- [ ] 담당자:
