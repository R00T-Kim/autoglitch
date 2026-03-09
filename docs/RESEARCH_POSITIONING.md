# AUTOGLITCH 연구 포지셔닝 / 차별점 메모

_Updated: 2026-03-09_

실행 계획은 `docs/ROADMAP.md`를 따른다.

> 구현 상태 메모(2026-03-09): backend-aware benchmark, artifact bundle, `chipwhisperer-hardware`
> 최소 통합은 소프트웨어적으로 구현되었다. 남은 핵심은 **실장비 evidence** 와
> **다중 backend/다중 board 실험 데이터** 다.

## 1. 문제의식
AUTOGLITCH의 연구 차별점은 **"fault injection을 할 수 있다"** 에 있지 않다.
그 자체는 이미 학계/산업계/오픈소스 생태계에서 널리 존재한다.

특히 아래는 이미 선행 사례가 충분하다.
- programmable glitching hardware/platform (예: ChipWhisperer 계열)
- scripted reproducible glitching workflow (예: SECGlitcher)
- low-cost Python-oriented glitching stacks (예: findus / PicoGlitcher)
- target-specific exploit PoC projects (예: stm32f1-picopwner, C8051F34x_Glitch)

따라서 AUTOGLITCH가 연구로서 설득력을 가지려면,
**새로운 glitch 물리나 새로운 펄스 생성 장비**가 아니라,
**이질적 fault injection 실험을 더 재현 가능하고, 비교 가능하고, 의미론적으로 다룰 수 있게 만드는 상위 프레임워크**를 목표로 삼아야 한다.

---

## 2. 우리가 메인 claim으로 잡아야 할 것

### 권장 메인 포지셔닝
> **AUTOGLITCH는 backend-independent, reproducible fault-injection experimentation framework이다.**

이를 한국어로 풀면:
> AUTOGLITCH는 특정 glitch 장비 자체를 대체하려는 도구가 아니라,
> **여러 glitch backend와 타깃을 공통 절차로 운영·비교·재현 가능하게 만드는 fault injection 실험 프레임워크**다.

---

## 3. 연구 차별점 후보

### 3.1 Backend-independent fault injection orchestration

#### 핵심 아이디어
ChipWhisperer, Raspberry Pi bridge, PicoGlitcher/findus 같은 **이질적 backend**를
하나의 실험 절차 안에서 다룰 수 있어야 한다.

#### 왜 연구 가치가 있나
기존 도구들은 각자 강력하지만 보통 **자기 장비 중심**이다.
AUTOGLITCH는 그 위에 올라가는 **상위 orchestration/control plane**이 될 수 있다.

#### 최소 요구조건
- 동일한 config semantics
- 동일한 run lifecycle
  - detect
  - setup
  - doctor
  - preflight
  - run
  - validate-hil-rc
- 동일한 report schema
- 동일한 benchmark task에서 backend 간 공정 비교 가능

#### 논문식 기여 문장 예시
> We present a backend-independent control plane for heterogeneous fault-injection hardware.

---

### 3.2 Reproducible fault-injection operations

#### 핵심 아이디어
기존 선행작은 “공격이 됐다”는 결과는 보여주지만,
**누가/언제/어떤 배선/어떤 보드 상태/어떤 환경에서 같은 결과를 재현할 수 있는가**를
체계적으로 다루는 경우는 드물다.

#### AUTOGLITCH가 할 수 있는 것
- preflight / doctor / queue / soak / lock / recovery drill
- config hash / git SHA / runtime fingerprint
- target metadata / wiring note / board prep note
- run bundle / lab evidence pack

#### 연구 주장 포인트
> fault injection 실험을 **운영 가능한(research-operable)** 형태로 표준화한다.

#### 논문식 기여 문장 예시
> We formalize a reproducibility-oriented operational workflow for fault-injection campaigns.

---

### 3.3 Semantics-aware fault modeling (fault-to-primitive)

#### 핵심 아이디어
기존 많은 툴은 결과를 대체로 아래처럼 본다.
- success / fail
- crash / reset
- target responded / target did not respond

하지만 공격 연구에서는 그보다 중요한 것이 있다.
> **이 fault가 어떤 공격 primitive로 이어질 수 있는가?**

#### AUTOGLITCH의 유리한 방향
이미 구조상 아래를 분리할 수 있다.
- `fault_class`
- `primitive`
- `execution.status`
- `reset_detected`
- `response_time`
- `error_code`

이걸 발전시키면 다음이 가능하다.
- instruction skip
- data corruption
- auth bypass
- boot bypass
- exploitable / non-exploitable fault 분리
- infra failure와 real fault 분리

#### 연구 주장 포인트
> fault injection 결과를 exploit-relevant semantics로 구조화한다.

#### 논문식 기여 문장 예시
> We introduce a semantics-aware result model that separates infrastructure failures from exploit-relevant fault primitives.

---

### 3.4 Health-aware closed-loop optimization

#### 핵심 아이디어
fault injection의 실제 실험 환경은 noisy하다.
- serial timeout
- stale binding
- bridge crash
- reset storm
- thermal drift
- board-to-board variance

일반적인 optimizer 비교는 이런 **실험실 인프라 불안정성**을 잘 다루지 않는다.

#### AUTOGLITCH가 연구로 밀 수 있는 방향
- optimizer 입력에 health/preflight/runtime telemetry 반영
- infra failure는 optimizer reward에 오염시키지 않음
- unstable environment에서도 time-to-first-valid-fault 개선

#### 연구 주장 포인트
> 실장비 불안정성을 고려한 robust fault injection optimization.

#### 논문식 기여 문장 예시
> We show that health-aware closed-loop optimization improves search robustness under unstable lab conditions.

---

## 4. 반대로 메인 novelty로 잡기 약한 것
다음은 공학적으로는 유용하지만, 단독으로는 연구 차별점이 약하다.

- "우리도 BO를 쓴다"
- "우리도 RL을 쓴다"
- "우리도 Raspberry Pi로 glitch bridge를 만들었다"
- "우리도 typed serial protocol을 만들었다"
- "우리도 plugin 구조다"

이런 항목은 **시스템 구현 요소**로는 좋지만,
논문 제목/메인 contribution의 중심에 놓기에는 약하다.

---

## 5. 우리가 피해야 할 claim
AUTOGLITCH는 아래를 주장하면 안 된다.

- 우리가 programmable fault injection의 최초다
- 우리가 reproducible glitching framework의 최초다
- 우리가 저가형 Python glitching stack의 최초다
- 우리가 ChipWhisperer 자동화의 최초다
- 우리가 target-specific glitch PoC의 최초다

대신 아래처럼 표현하는 것이 적절하다.

> AUTOGLITCH는 기존 fault injection 도구와 PoC를 포괄하는
> **실험 운영/비교/재현성 프레임워크**다.

---

## 6. 가장 추천하는 연구 서사

### 메인 서사
> fault injection 도구는 많지만,
> **이질적 backend를 공통 절차로 운영하고,
> 그 결과를 재현 가능하게 보관하며,
> fault를 exploit semantics 수준으로 비교하는 프레임워크는 부족하다.**

### AUTOGLITCH의 제안
1. backend-independent orchestration
2. reproducibility-oriented operations
3. semantics-aware result modeling
4. health-aware closed-loop optimization

이 네 개를 묶으면 단순한 “glitch tool”이 아니라,
**fault injection experimentation system**이라는 포지션이 성립한다.

---

## 7. 논문 contribution 후보

### 버전 A — systems / framework 논문
1. heterogeneous FI backends를 위한 공통 control plane
2. reproducibility-focused run bundle / validation workflow
3. semantics-aware result schema
4. multi-backend / multi-target benchmark study

### 버전 B — experimental methodology 논문
1. fault injection 실험 재현성 프로토콜 제안
2. infra failure와 exploit-relevant fault를 분리하는 result model
3. operator- and lab-aware evaluation methodology
4. backend/target across-study benchmark

### 버전 C — optimization 논문
1. health-aware optimization objective
2. semantic feedback 기반 reward structuring
3. unstable lab conditions에서 robust search 평가
4. random/grid/GA/BO/RL comparative study

---

## 8. 평가 설계도 차별점과 맞춰야 한다

### 최소 평가축
- backend 2종 이상
  - Raspberry Pi bridge
  - ChipWhisperer 또는 findus/PicoGlitcher
- target 2종 이상
  - STM32F3
  - STM32F1 또는 ESP32
- 실험 task 3종 이상
  - detectable fault generation
  - reset/boot perturbation
  - security-check bypass or equivalent exploit-oriented task

### 최소 지표
- time-to-first-valid-fault
- time-to-first-primitive
- fault yield
- primitive yield
- infra failure rate
- preflight pass rate
- reproducibility across seeds / boards / days
- operator intervention count

### 있으면 강해지는 지표
- board-to-board variance
- thermal drift sensitivity
- backend portability overhead
- run bundle completeness / replayability

---

## 9. 지금 당장 해야 할 연구 우선순위

### P0
1. ChipWhisperer backend adapter 설계/구현
2. Raspberry Pi bridge 실장비 evidence pack 확보
3. 공통 benchmark schema 초안 작성

### P1
1. findus/PicoGlitcher backend 추가 또는 bridge 연동
2. artifact bundle 자동 생성
3. wiring / board prep / lab metadata schema 추가

### P2
1. random / grid / GA / BO / RL 공정 비교
2. fault-to-primitive labeling 기준 고도화
3. benchmark report / dataset 공개

---

## 10. 한 문장으로 정리한 차별점

### 가장 추천
> **AUTOGLITCH는 여러 glitch backend를 공통 절차로 운영·비교·재현 가능하게 만들고,
> fault를 exploit-relevant primitive 수준으로 구조화하는 fault injection experimentation framework이다.**

### 짧은 버전
> **실험 운영성 + 재현성 + 의미론적 fault 모델링**이 AUTOGLITCH의 핵심 차별점이다.

---

## 11. 내부 의사결정용 메모
앞으로 설계 선택에서 아래 질문에 “예”를 만들면 연구 차별점이 강화된다.

1. 이 기능이 backend-independent한가?
2. 이 기능이 재현성/운영성에 기여하는가?
3. 이 기능이 fault semantics를 더 잘 보존하는가?
4. 이 기능이 multi-target / multi-backend 비교를 쉽게 만드는가?
5. 이 기능이 실장비 evidence를 더 잘 남기게 만드는가?

반대로 아래에 해당하면 우선순위를 낮춰도 된다.
- 단일 backend 전용 convenience feature
- 연구 claim과 무관한 UI 성격 개선
- 단순 기능 추가지만 benchmark나 reproducibility에 연결되지 않는 변경
