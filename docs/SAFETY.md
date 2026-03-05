# Safety & Recovery Policy

## 목적
장비 보호와 장시간 실험 안정성을 위해 모든 trial 전후에 안전 제약과 복구 정책을 강제한다.

## SafetyController

### 제한값
- `width_min/max`
- `offset_min/max`
- `voltage_abs_max`
- `repeat_min/max`
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
- HIL에서는 `hardware: serial` + `safety` 보수적 설정
- soak/queue 실행 전 반드시 `validate-config` 통과
- `manifest_<run_id>.json`에 config hash/plugin snapshot을 보관해 재현성 확보
