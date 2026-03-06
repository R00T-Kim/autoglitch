# Safety & Recovery Policy

## 목적
장비 보호와 장시간 실험 안정성을 위해 모든 trial 전후에 안전 제약과 복구 정책을 강제한다.

## SafetyController

### 제한값
- `width_min/max`
- `offset_min/max`
- `voltage_abs_max`
- `repeat_min/max`
- `ext_offset_min/max`
- `min_cooldown_s`
- `max_trials_per_minute`
- `auto_throttle`

### 동작
1. optimizer 제안값을 `sanitize_params()`로 안전범위로 클램프
2. `pre_trial()`에서 cooldown/rate-limit 검사
3. trial 후 `post_trial()`로 실행 시각 기록
4. 위반 시 `SafetyViolation` 발생, 오케스트레이터는 안전 파라미터 fallback 적용

## RecoveryExecutor

### Retry
- `max_attempts`
- `initial_backoff_s`
- `max_backoff_s`
- `backoff_multiplier`
- `jitter_s`

### Circuit Breaker
- `failure_threshold`
- `recovery_timeout_s`
- 상태: `closed -> open -> half_open`

연속 실패 임계치 도달 시 회로를 열고(`open`) 호출 차단.
`recovery_timeout_s` 경과 후 `half_open`에서 단일 시도 허용.

## CLI 점검
```bash
python -m src.cli validate-config --target stm32f3
```

## 운영 권장
- local binding은 `configs/local/hardware.yaml`에 저장되며, 실험 설정과 분리된 머신 전용 상태로 취급
- 새 HIL 온보딩 명령: `detect-hardware`, `setup-hardware`, `doctor-hardware`
- 기본 권장 프로토콜은 typed serial `autoglitch.v1`, legacy serial text는 fallback
- HIL에서는 `hardware: serial` + `safety` 보수적 설정
- strict config는 `config_version: 3`를 기준으로 `ext_offset`/`recovery`와 hardware binding/discovery 필드를 함께 검증
- soak/queue 실행 전 반드시 `validate-config` 통과
- `manifest_<run_id>.json`에 config hash/plugin snapshot을 보관해 재현성 확보

### Serial async 운용 가이드
- `hardware.serial.keep_open: true`로 trial 간 연결 재사용(지연 감소)
- `reconnect_attempts`, `reconnect_backoff_s`로 일시적 UART 오류 복구
- 장비가 불안정할 때는 `min_cooldown_s`, `max_trials_per_minute`를 함께 보수적으로 설정

### HIL preflight 게이트
- 실행: `python -m src.cli hil-preflight --target stm32f3` 또는 `--hardware serial-json-hardware --serial-port /dev/ttyUSB0`
- 강제 실행: `run/soak/queue-run`에 `--require-preflight` 추가
- 기준값(기본):
  - `hardware.serial.preflight.max_timeout_rate: 0.05`
  - `hardware.serial.preflight.max_reset_rate: 0.10`
  - `hardware.serial.preflight.max_p95_latency_s: 0.50`

### 하드웨어 온보딩 안전 절차
- 지원 장비는 먼저 `detect-hardware` → `setup-hardware` → `doctor-hardware` 순서로 바인딩
- 로컬 바인딩 파일(`configs/local/hardware.yaml`)은 머신별 상태로 취급하고 버전관리 대상에 포함하지 않음
- typed serial(`autoglitch.v1`)이 기본 권장 경로이며 legacy text serial은 호환용 fallback
