# AUTOGLITCH Benchmark Schema v1

_Updated: 2026-03-09_

> 구현 상태 메모(2026-03-09): benchmark CLI는 현재 **backend × algorithm** 비교,
> benchmark/comparison report 생성, per-run artifact bundle 연결까지 지원한다.
> 남은 것은 실장비 반복 데이터 축적과 논문용 plot/표 정리다.

## 1. 목적
이 문서는 AUTOGLITCH의 연구 차별점 중 아래 두 가지를 실험 가능하게 만드는 **공통 benchmark 규약**이다.

- backend-independent orchestration
- reproducible fault-injection evaluation

즉, 특정 장비나 특정 타깃에서 “한 번 성공했다”를 기록하는 것이 아니라,
**여러 backend / 여러 target / 여러 날짜 / 여러 보드에서 공정 비교 가능한 실험 단위**를 정의한다.

관련 문서:
- `docs/RESEARCH_POSITIONING.md`
- `docs/ROADMAP.md`
- `docs/ARTIFACT_BUNDLE_SCHEMA.md`

---

## 2. 설계 원칙

1. **동일한 task 정의**가 backend마다 유지되어야 한다.
2. success/fail만이 아니라 **fault semantics**까지 비교 가능해야 한다.
3. 결과는 반드시 **artifact bundle**과 연결되어야 한다.
4. benchmark는 단발 demo가 아니라 **반복 측정**을 전제로 한다.
5. benchmark metric은 가능한 한 **장비 의존적인 표현**이 아니라 실험 의미론적 표현을 사용한다.

---

## 3. Benchmark 단위 정의

하나의 benchmark run은 아래 다섯 축으로 정의한다.

| 축 | 설명 | 예시 |
| --- | --- | --- |
| backend | glitch backend / bridge / 장비 | `pi-bridge`, `chipwhisperer-hardware`, `picoglitcher-hardware` |
| target | 타깃 보드/칩/보호 상태 | `stm32f3_nucleo`, `stm32f1_bluepill_rdp1`, `esp32_secureboot` |
| task | 실험 목적 | `det_fault`, `reset_boot`, `sec_check_bypass` |
| campaign policy | 탐색 방식 | `random`, `grid`, `ga`, `bo`, `rl` |
| repetition context | 반복 조건 | seed / board_id / day / operator |

---

## 4. Task taxonomy v1

### 4.1 `det_fault` — Detectable fault generation
가장 낮은 난도의 benchmark.

#### 목적
- reset/crash/unknown이 아닌 **관측 가능한 fault**를 일정 확률 이상 발생시키는지 측정

#### 성공 기준
- `fault_class != NORMAL`
- infra failure / blocked는 성공으로 치지 않음

#### 추천 용도
- backend bring-up
- preflight 이후 smoke benchmark
- optimizer baseline 비교

---

### 4.2 `reset_boot` — Reset/boot perturbation
부트/리셋 경로를 교란하되, 단순 연결 실패와 구분되는 결과를 측정

#### 목적
- reset-only, delayed boot, unstable boot, boot-sequence perturbation 등을 구분

#### 성공 기준
다음 중 하나를 만족:
- reset 후 비정상 boot signature
- expected boot line mismatch
- boot timing anomaly가 설정 임계치 이상

#### 추천 용도
- backend timing 품질 비교
- reset/trigger wiring 품질 검증
- 초기 타깃별 benchmark

---

### 4.3 `sec_check_bypass` — Security-check bypass
exploit-oriented benchmark.

#### 목적
- secure boot / auth check / debug lock / readout protection 등
  **공격 의미가 있는 primitive**로 이어지는지 측정

#### 성공 기준
- `primitive.type != NONE`
- 또는 benchmark-defined exploit witness 충족

#### 예시 witness
- 보호된 읽기/쓰기가 가능해짐
- boot verification이 우회됨
- auth gate 없이 privileged path 진입

---

## 5. Repetition 규칙

AUTOGLITCH benchmark는 기본적으로 아래 세 층의 반복을 요구한다.

### 5.1 Seed repetition
- 동일 setup에서 seed만 바꿔 반복
- 목적: optimizer/randomness 민감도 측정
- 기본 권장: **3 seeds 이상**

### 5.2 Board repetition
- 같은 target family에서 물리 보드를 바꿔 반복
- 목적: board-to-board variance 측정
- 기본 권장: **2 boards 이상**

### 5.3 Day repetition
- 다른 날짜/세션에서 반복
- 목적: day-to-day reproducibility 측정
- 기본 권장: **2 days 이상**

### 최소 benchmark 기준
아래를 충족해야 benchmark 결과로 인정한다.
- 1 backend × 1 target × 1 task 당
  - 3 seeds
  - 2 boards
  - 2 days

초기 PoC 단계에서는 완화 가능하지만, 논문/보고용 수치에는 이 기준을 권장한다.

---

## 6. 필수 메트릭

### 6.1 Fault-level metrics
| 이름 | 정의 |
| --- | --- |
| `fault_yield` | 전체 trial 중 `fault_class != NORMAL` 비율 |
| `valid_fault_yield` | infra failure/blocked 제외 후 유효 fault 비율 |
| `reset_rate` | `fault_class == RESET` 비율 |
| `crash_rate` | `fault_class == CRASH` 비율 |
| `infra_failure_rate` | `execution.status == infra_failure` 비율 |
| `blocked_rate` | `execution.status == blocked` 비율 |

### 6.2 Primitive-level metrics
| 이름 | 정의 |
| --- | --- |
| `primitive_yield` | 전체 trial 중 `primitive.type != NONE` 비율 |
| `primitive_repro_rate` | 동일 설정 재실행 시 같은 primitive가 반복적으로 나온 비율 |
| `time_to_first_primitive` | 첫 primitive 발견까지 걸린 trial 수 / 시간 |
| `primitive_distribution` | primitive type 분포 |

### 6.3 Operational metrics
| 이름 | 정의 |
| --- | --- |
| `time_to_first_valid_fault` | 첫 유효 fault 발견까지 걸린 trial 수 / 시간 |
| `preflight_pass_rate` | 동일 setup 반복 시 preflight 통과율 |
| `operator_intervention_count` | 실험 중 수동 개입 횟수 |
| `bundle_completeness_rate` | 필수 artifact bundle 항목 충족률 |
| `backend_portability_overhead` | backend 교체 시 추가 setup/patch/metadata 비용 |

### 6.4 Robustness metrics
| 이름 | 정의 |
| --- | --- |
| `seed_variance` | seed 변화에 따른 primitive yield 분산 |
| `board_variance` | board 변화에 따른 결과 분산 |
| `day_variance` | 날짜/세션 변화에 따른 결과 분산 |
| `latency_stability` | response time 분포 안정성 |

---

## 7. 최소 결과 스키마

각 benchmark summary는 최소 아래 필드를 가져야 한다.

```yaml
benchmark_id: bm_20260309_stm32f3_pi_detfault_v1
schema_version: 1
backend: pi-bridge
target: stm32f3_nucleo
task: det_fault
campaign_policy: bo
seeds: [11, 12, 13]
boards: [board_a, board_b]
days: [2026-03-09, 2026-03-10]
metrics:
  fault_yield: 0.21
  primitive_yield: 0.03
  time_to_first_valid_fault_trials: 14
  time_to_first_primitive_trials: 88
  infra_failure_rate: 0.01
  primitive_repro_rate: 0.67
artifact_bundles:
  - experiments/results/bundles/20260309/bm_.../run_01
  - experiments/results/bundles/20260309/bm_.../run_02
notes:
  target_prep: c12_removed
  wiring_profile: wf_stm32f3_pi_v1
```

---

## 8. Benchmark profile 권장 집합

### 최소 연구 benchmark 세트

| benchmark_id | backend | target | task | 목적 |
| --- | --- | --- | --- | --- |
| `bm_pi_stm32f3_detfault_v1` | Pi bridge | STM32F3 | `det_fault` | backend baseline |
| `bm_cw_stm32f3_detfault_v1` | ChipWhisperer | STM32F3 | `det_fault` | 기준선 비교 |
| `bm_pi_stm32f3_resetboot_v1` | Pi bridge | STM32F3 | `reset_boot` | timing / reset benchmark |
| `bm_cw_stm32f3_resetboot_v1` | ChipWhisperer | STM32F3 | `reset_boot` | timing / reset 비교 |
| `bm_pi_stm32f1_secbypass_v1` | Pi bridge | STM32F1 | `sec_check_bypass` | exploit-oriented benchmark |
| `bm_cw_stm32f1_secbypass_v1` | ChipWhisperer | STM32F1 | `sec_check_bypass` | exploit benchmark 비교 |

### 확장 benchmark 세트
- `picoglitcher` backend 추가
- `esp32_secureboot` target 추가
- unstable-condition benchmark 추가
  - artificial timeout
  - reconnect noise
  - thermal drift

---

## 9. 공정 비교 규칙

backend 간 benchmark를 비교할 때 아래를 맞춘다.

1. 동일 target firmware / 보호 상태
2. 동일 target prep 상태
3. 동일 repetition rule
4. 동일 success/primitive criterion
5. 동일 artifact completeness rule
6. 동일 reporting schema

### 허용되는 차이
- backend-specific parameter mapping
- backend-specific preflight detail
- backend-specific safety limits

### 허용되지 않는 차이
- backend마다 다른 success 정의
- backend마다 다른 primitive 정의
- 어떤 backend만 evidence 없이 결과만 주장

---

## 10. 실험 결과 해석 규칙

### 강한 결과
- primitive yield 차이가 유의미함
- 재현성(day/board/seed) 차이가 명확함
- infra failure를 분리했을 때도 결과가 유지됨
- artifact bundle이 충분해 제3자 검토 가능

### 약한 결과
- 한 번 성공한 screenshot만 있음
- success/fail만 기록하고 primitive 정보 없음
- board/day 반복이 없음
- backend가 바뀌면 비교가 불가능함

---

## 11. 구현 우선순위 연결

### 바로 필요한 구현
1. benchmark spec loader / validator
2. benchmark summary writer
3. artifact bundle path linking
4. primitive taxonomy 문서/코드 정합성
5. repetition metadata(seed/day/board/operator) 강제 기록

### 이후 필요한 구현
1. benchmark config templates
2. backend matrix runner
3. compare-report generator
4. figure/table export pipeline

---

## 12. 한 줄 요약

> AUTOGLITCH benchmark는 “한 번 glitch가 먹혔다”를 기록하는 체계가 아니라,
> **여러 backend와 타깃에서 fault/primitive/운영성/재현성을 공정 비교하기 위한 공통 실험 규약**이다.
