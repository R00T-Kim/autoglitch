# AUTOGLITCH Research Roadmap

_Updated: 2026-03-09_

## 0. 이 문서의 역할
이 문서는 아래 두 문서를 **실행 계획으로 연결**하는 로드맵이다.

- `docs/RELATED_RESEARCH.md`
- `docs/RESEARCH_POSITIONING.md`

즉, 이 문서는 단순 기능 TODO가 아니라,
**AUTOGLITCH가 어떤 연구 차별점을 목표로 삼고, 그 차별점을 입증하기 위해 앞으로 무엇을 어떤 순서로 해야 하는지**를 정리한다.

---

## 1. North Star

### 메인 연구 포지셔닝
> **AUTOGLITCH는 backend-independent, reproducible fault-injection experimentation framework이다.**

### 우리가 최종적으로 보여줘야 하는 것
1. 서로 다른 glitch backend를 공통 절차로 운영할 수 있다.
2. 실험 결과를 재현 가능한 bundle/evidence 형태로 남길 수 있다.
3. 단순 success/fail이 아니라 exploit-relevant primitive 수준으로 결과를 구조화할 수 있다.
4. noisy lab 환경에서도 robust하게 탐색/최적화할 수 있다.

---

## 2. 무엇을 목표로 하고, 무엇을 목표로 하지 않는가

### 연구 목표
- **Backend-independent orchestration**
- **Reproducible operations**
- **Semantics-aware fault modeling**
- **Health-aware optimization**
- **Multi-backend / multi-target benchmark**

### 비목표(Non-goals)
아래는 구현해도 좋지만, 현재 연구 차별점의 중심은 아니다.
- LLM 기능을 더 화려하게 만드는 것
- UI/UX 편의 기능 추가
- 단일 백엔드 전용 convenience 기능
- benchmark/evidence 없이 새로운 optimizer만 늘리는 것
- 실험 의미론과 무관한 config 확장

---

## 3. 연구 claim ↔ 구현 항목 매핑

| 연구 claim | 필요한 구현 | 필요한 증거 |
| --- | --- | --- |
| backend-independent orchestration | ChipWhisperer / Pi bridge / findus 계열 공통 adapter contract | 동일 config/task를 여러 backend에서 실행한 결과 |
| reproducible operations | artifact bundle, board prep metadata, wiring metadata, preflight/doctor/RC | day/board/seed 반복 결과 + evidence pack |
| semantics-aware modeling | `fault_class`, `primitive`, `execution.status` 스키마 고정 | primitive-level benchmark / labeling / 분포 보고 |
| health-aware optimization | preflight/runtime telemetry를 optimizer context에 반영 | unstable 환경에서 TTFF/primitive yield 개선 |
| benchmark framework | 공통 task, 공통 metrics, 공통 report | multi-backend / multi-target 비교표 |

---

## 4. 현재 상태 (2026-03-09)

### 이미 확보된 기반
- strict config / safety / recovery baseline
- queue / soak / replay / benchmark 경로
- serial HIL preflight (`hil-preflight`, `--require-preflight`)
- hardware framework + local binding + doctor/setup/detect
- typed serial path (`serial-json-hardware`, `autoglitch.v1`)
- plugin-based runtime component wiring(observer/classifier/mapper)
- infra failure와 experiment outcome 분리
- campaign summary에 execution status / planner/advisor backend 기록
- backend-aware benchmark(`backend × algorithm`) compare path
- artifact bundle generator + bundle completeness
- ChipWhisperer backend(`chipwhisperer-hardware`) 최소 통합
- benchmark / lab metadata strict schema
- full-repo software gate green

### 아직 부족한 핵심
- findus/PicoGlitcher backend 부재
 - board prep / wiring / lab metadata의 실장비 운영 데이터 축적 부족
- benchmark suite 부재
- 실장비 evidence pack 부족
- primitive taxonomy와 labeling 기준의 고도화 부족

---

## 5. 실행 원칙

앞으로의 구현은 아래 원칙을 만족해야 한다.

1. **새 기능보다 공통 실험 절차를 우선한다.**
2. **단일 backend 최적화보다 backend-independent abstraction을 우선한다.**
3. **실행 성공보다 evidence 생성 가능성을 우선한다.**
4. **성공/실패보다 fault semantics 보존을 우선한다.**
5. **새 optimizer보다 benchmark 가능한 운영 모델을 우선한다.**

---

## 6. 단계별 로드맵

# Phase 0 — 연구 기준선 고정 (즉시 ~ 2주) ✅ software baseline complete

## 목표
연구 차별점과 직접 연결되는 **공통 스키마 / 공통 메트릭 / 공통 아티팩트 규약**을 먼저 고정한다.

## 핵심 산출물
- benchmark schema v1
- run bundle schema v1
- lab evidence pack directory convention
- primitive taxonomy v1
- board prep / wiring metadata v1

초기 문서 산출물:
- `docs/BENCHMARK_SCHEMA.md`
- `docs/ARTIFACT_BUNDLE_SCHEMA.md`

## 구체 작업
1. `docs/`에 benchmark spec 추가
   - target
   - backend
   - task
   - success criterion
   - primitive criterion
   - repetition rule
2. artifact bundle 명세 추가
   - config hash
   - git SHA
   - runtime fingerprint
   - preflight report
   - manifest
   - campaign summary
   - trial log
   - decision trace
   - optional scope/logic analyzer asset path
3. primitive taxonomy 문서화
   - instruction skip
   - data corruption
   - auth bypass
   - boot bypass
   - exploitable / non-exploitable
   - infra failure / blocked / reset-only
4. metadata schema 문서화
   - target board revision
   - operator
   - wiring note
   - board prep note
   - power supply note

## Exit criteria
- 같은 실험을 수행했을 때 **무엇을 저장해야 하는지** 문서만 보고 모두 알 수 있음
- benchmark와 artifact bundle이 문서 기준으로 재현 가능

## 연구 차별점 연결
- reproducible operations
- semantics-aware modeling

---

# Phase 1 — 첫 번째 이종 backend 확보 (2주 ~ 6주) ✅ first backend complete

## 목표
현재 Raspberry Pi bridge 중심 구조에 **ChipWhisperer backend**를 정식으로 연결한다.

## 왜 ChipWhisperer가 우선인가
- 가장 강한 선행 기준선이다.
- 상용/연구 생태계에서 인지도가 높다.
- 이걸 붙여야 AUTOGLITCH의 “상위 control plane” 포지션이 설득력을 얻는다.

## 핵심 산출물
- `chipwhisperer-hardware` adapter/plugin
- detect/setup/doctor/preflight/run 연결
- ChipWhisperer-specific metadata 캡처
- Pi bridge vs ChipWhisperer single-target smoke benchmark

설계 문서:
- `docs/CHIPWHISPERER_ADAPTER_PLAN.md`

## 구체 작업
1. adapter/plugin 설계
   - capability model
   - target support declaration
   - glitch/reset/trigger abstraction mapping
2. CW detect/setup/doctor 경로 구현
3. preflight에서 CW-specific health/parameter sanity 추가
4. run/report에서 CW 메타데이터 저장
5. 동일 target(STM32F3)에서
   - Pi bridge
   - ChipWhisperer
   두 backend를 공통 schema로 실행

## Exit criteria
- 동일 benchmark config가 Pi bridge와 ChipWhisperer에서 모두 실행됨
- 결과가 동일 report schema로 저장됨
- backend portability overhead를 측정할 수 있음

## 연구 차별점 연결
- backend-independent orchestration
- benchmarkable control plane

---

# Phase 2 — 실장비 evidence pack과 run bundle 완성 (4주 ~ 8주) ◐ software complete / lab evidence pending

## 목표
“돌아간다” 수준이 아니라, **논문/보고/재현실험에 제출 가능한 evidence package**를 자동으로 만든다.

## 핵심 산출물
- artifact bundle generator
- `validate-hil-rc`와 bundle 연결
- evidence pack example 1세트 이상
- 사진/배선/파형 경로까지 포함한 run bundle

## 구체 작업
1. run 종료 시 bundle 생성
2. RC validation 결과 자동 포함
3. wiring / board prep / operator metadata 입력 경로 추가
4. scope/logic analyzer asset path를 report에 연결
5. `experiments/results/real_hardware/...` 표준화

## Exit criteria
- 한 번의 실장비 실험이 **folder 하나**로 재현 가능하게 보관됨
- operator가 바뀌어도 artifact만 보고 실험 맥락을 이해 가능

## 연구 차별점 연결
- reproducible operations
- research-operable workflow

---

# Phase 3 — fault semantics와 primitive taxonomy 고도화 (6주 ~ 10주)

## 목표
단순 success/fail을 넘어서, AUTOGLITCH의 결과를 **공격 의미론 수준**으로 비교 가능하게 만든다.

## 핵심 산출물
- primitive taxonomy v2
- labeling guideline
- classifier/mapper 고도화
- primitive-level report and benchmark

## 구체 작업
1. fault class와 primitive 정의를 문서/코드에서 일치시킴
2. `primitive == none` / `faulted-but-non-exploitable` 구분 강화
3. infra failure / blocked / reset-only와 진짜 primitive 분리
4. benchmark report에 다음 포함
   - time-to-first-valid-fault
   - time-to-first-primitive
   - primitive reproducibility rate
   - primitive distribution

## Exit criteria
- 보고서가 “fault가 났다”가 아니라 “어떤 primitive가 나왔는가”를 말할 수 있음
- backend/target 간 primitive yield 비교 가능

## 연구 차별점 연결
- semantics-aware fault modeling
- exploit-relevant result schema

---

# Phase 4 — health-aware optimization 연구화 (8주 ~ 12주)

## 목표
실험실 불안정성을 모델에 반영한 **robust optimization**으로 연결한다.

## 핵심 산출물
- health-aware reward/context design
- optimizer comparison report
- unstable-condition benchmark

## 구체 작업
1. optimizer context에 health 정보 반영
   - preflight quality
   - latency
   - reset rate
   - infra failure frequency
   - recovery state
2. 비교 실험
   - random
   - grid
   - GA(필요 시)
   - BO
   - RL
3. unstable condition 실험 설계
   - timeout 증가
   - reset storm
   - reconnect noise
   - thermal drift

## Exit criteria
- noisy lab 조건에서 robust strategy가 baseline보다 낫다는 결과 확보
- infra failure contamination을 줄였다는 수치 제시 가능

## 연구 차별점 연결
- health-aware closed-loop optimization

---

# Phase 5 — 두 번째 외부 backend와 다중 타깃 확장 (10주 ~ 16주)

## 목표
AUTOGLITCH가 단지 CW wrapper가 아니라는 점을 보여주기 위해,
**findus/PicoGlitcher 계열 또는 다른 저비용 backend**까지 흡수한다.

## 핵심 산출물
- second external backend adapter/bridge
- multi-backend benchmark results
- STM32F3 + STM32F1/ESP32 dual-target study

## 구체 작업
1. findus/PicoGlitcher adapter 또는 protocol bridge 구현
2. target 추가
   - STM32F1 또는 ESP32
3. 동일 benchmark task 반복
4. backend × target 매트릭스 비교표 작성

## Exit criteria
- 최소 2 backend × 2 target 비교 가능
- portability / reproducibility / primitive yield 비교표 완성

## 연구 차별점 연결
- backend neutrality
- benchmark framework
- generalization

---

# Phase 6 — 논문 패키지 / 공개 자산 정리 (마지막 단계)

## 목표
논문/아티팩트 평가/오픈소스 공개에 필요한 형태로 결과를 정리한다.

## 핵심 산출물
- paper figure/table generation scripts
- benchmark dataset
- artifact evaluation instructions
- minimal reproducible package

## 구체 작업
1. figure/table 자동 생성 스크립트
2. benchmark raw + processed data 정리
3. artifact evaluation 문서 작성
4. “claim ↔ evidence” 매핑 표 작성

## Exit criteria
- 논문 초안의 모든 claim이 artifact/dataset로 연결됨
- 제3자가 최소 1개 benchmark를 재실행 가능

---

## 7. 우선순위 표

| 우선순위 | 해야 할 것 | 이유 |
| --- | --- | --- |
| P0 | benchmark schema / bundle schema / metadata schema 고정 | 연구 방향을 코드와 맞추기 위해 |
| P0 | ChipWhisperer backend | 가장 강한 선행 기준선 흡수 |
| P0 | Raspberry Pi 실장비 evidence pack | 현재 weakest link 보완 |
| P1 | artifact bundle 자동 생성 | reproducibility claim의 핵심 |
| P1 | primitive taxonomy 강화 | semantics-aware claim의 핵심 |
| P1 | optimizer health context 비교 | optimization claim의 기반 |
| P2 | findus/PicoGlitcher backend | backend-neutral claim 강화 |
| P2 | dual-target benchmark | generalization 확보 |

---

## 8. 성공 판단 기준

### 연구적으로 성공했다고 말하려면
아래를 만족해야 한다.

1. **최소 2개 backend**에서 동일 benchmark 실행 가능
2. **최소 2개 target**에서 동일 schema로 결과 저장 가능
3. 각 run이 **artifact bundle**로 보관됨
4. 결과가 **primitive-level**로 비교 가능
5. **reproducibility / robustness / portability** 지표가 수치로 제시됨

### 아직 성공이 아닌 상태
- 한 backend에서만 돌아감
- 한 target PoC만 성공함
- 실험 성공은 했지만 artifact/bundle이 없음
- primitive 대신 success/fail만 기록함
- benchmark 정의 없이 ad-hoc demo만 있음

---

## 9. 앞으로 기능 우선순위를 판단하는 질문

새 기능을 넣기 전에 아래를 물어본다.

1. 이 기능이 **backend-independent** 한가?
2. 이 기능이 **reproducibility** 를 올리는가?
3. 이 기능이 **fault semantics** 를 더 잘 보존하는가?
4. 이 기능이 **multi-backend / multi-target benchmark** 에 도움이 되는가?
5. 이 기능이 **실장비 evidence** 를 더 잘 남기게 하는가?

3개 이상 “예”면 우선순위가 높다.
그렇지 않으면 뒤로 미뤄도 된다.

---

## 10. 권장 다음 액션 (바로 실행)

### 이번 주
1. `docs/`에 benchmark schema 초안 추가
2. artifact bundle schema 초안 추가
3. ChipWhisperer adapter 설계 문서 작성
4. Raspberry Pi 실장비 1차 evidence pack 폴더 구조 생성

### 이번 달
1. ChipWhisperer backend PoC 구현
2. Pi bridge vs ChipWhisperer 단일 타깃 비교
3. run bundle 자동 생성기 구현
4. primitive taxonomy v1 고정

### 그 다음
1. second backend(findus/PicoGlitcher) 추가
2. dual-target benchmark 수행
3. health-aware optimizer 비교 실험 수행
4. 논문용 figure/table pipeline 준비

---

## 11. 한 문장 결론

> AUTOGLITCH는 새로운 glitch 장비를 만드는 프로젝트가 아니라,
> **서로 다른 fault injection backend를 공통 절차로 운영·비교·재현하고,
> 그 결과를 exploit semantics 수준으로 구조화하는 연구용 실험 프레임워크**로 발전해야 한다.
