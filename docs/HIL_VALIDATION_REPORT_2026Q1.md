# HIL Validation Report 2026 Q1

> 상태(2026-03-06): **실측 데이터 대기 중**. 아래 템플릿은 유지하되, 현재 확보된 근거는 software-only validation뿐이다.
> software gate(2026-03-06): `pytest -q` → `93 passed, 2 skipped`

## 1) 목적
STM32F3/ESP32 타깃에서 AUTOGLITCH의 serial HIL 실행 안정성과 재현성 KPI를 검증한다.

## 2) Protocol
0. Software gate:
   - strict config v2 validation 통과
   - async serial running-event-loop regression 통과
   - queue/soak serial parallel guard regression 통과
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
- Preflight report: TBD (lab measurement required)
- Campaign summaries: TBD
- Aggregate: TBD
- Gate pass/fail: TBD

## 5) ESP32 결과
- Preflight report: TBD (lab measurement required)
- Campaign summaries: TBD
- Aggregate: TBD
- Gate pass/fail: TBD

## 6) 이슈 및 대응
- UART 노이즈:
- 전원 안정성:
- 장비 재부팅/쿨다운 정책:

## 7) 결론
- Release candidate 판단: software readiness는 상승했지만, **HIL release candidate 판정은 아직 불가**
- 다음 액션:
  - lab에서 `hil-preflight` / repro / soak 결과를 실제 숫자로 채우기
  - trace JSONL / campaign summary / preflight summary 경로를 본 문서에 첨부하기
