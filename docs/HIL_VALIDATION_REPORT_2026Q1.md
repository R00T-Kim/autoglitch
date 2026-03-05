# HIL Validation Report 2026 Q1

> 상태: Template (실측 데이터 입력 필요)

## 1) 목적
STM32F3/ESP32 타깃에서 AUTOGLITCH의 serial HIL 실행 안정성과 재현성 KPI를 검증한다.

## 2) Protocol
1. `hil-preflight` 통과 (`--require-preflight` 조건)
2. Warmup: 100 trials
3. Stability: 3회 × 300 trials (고정 seed 세트)
4. Repro: 5회 × 200 trials

## 3) Gate Criteria
- `primitive_repro_rate_mean >= 0.20`
- `success_rate_mean >= 0.30`
- `latency.p95_seconds <= 0.50`
- `runtime.throughput_trials_per_second` 기준선 대비 -20% 이내
- `error_breakdown.runtime_failure` 비율 <= 0.15

## 4) STM32F3 결과
- Preflight report:
- Campaign summaries:
- Aggregate:
- Gate pass/fail:

## 5) ESP32 결과
- Preflight report:
- Campaign summaries:
- Aggregate:
- Gate pass/fail:

## 6) 이슈 및 대응
- UART 노이즈:
- 전원 안정성:
- 장비 재부팅/쿨다운 정책:

## 7) 결론
- Release candidate 판단:
- 다음 액션:
