# Fault Injection 관련 선행연구 / 도구 / 소형 프로젝트 정리

_업데이트: 2026-03-09_

> 구현 상태 메모(2026-03-09): 이 문서에서 도출한 소프트웨어 우선순위 중
> benchmark schema, artifact bundle, ChipWhisperer 1차 backend 통합은 구현되었다.
> 아직 증거가 부족한 부분은 실장비 multi-day / multi-board 데이터다.

선행연구 정리를 실제 실행 계획으로 연결한 문서는 `docs/ROADMAP.md`를 참고한다.

## TL;DR
- **AUTOGLITCH가 fault injection 자동화의 첫 시도는 아니다.**
- 이미 **ChipWhisperer**, **SECGlitcher**, **findus/PicoGlitcher**, 각종 **타깃별 glitch PoC 레포**가 존재한다.
- 따라서 AUTOGLITCH의 차별점은 **새로운 glitch 원리**가 아니라,
  **하드웨어 비종속 오케스트레이션 + 운영/재현성 + 표준화된 실험 관리 + fault-to-primitive 추상화**에 두는 것이 맞다.

---

## 1) 현재 확인된 핵심 선행축

### 1.1 ChipWhisperer 생태계: 가장 강한 기준선

#### 확인한 사실
- ChipWhisperer 공식 문서는 **Husky / Pro / Lite / Nano**의 기능 비교를 제공하며,
  이 중 **voltage glitching은 전 제품군**, **clock glitching은 Husky / Pro / Lite**에서 지원된다고 설명한다.
- 공식 **scope API**는 `scope.glitch` 하위에서 width/offset/ext_offset/repeat/output/trigger source와
  crowbar 관련 IO(`glitch_hp`, `glitch_lp`)를 포함한 제어 API를 노출한다.
- 공식 튜토리얼은 **Jupyter notebook** 중심이고, 문서에 따르면 notebook 출력은
  개발 브랜치 기준으로 **정기적으로 실제 하드웨어에서 테스트**된다.
- `chipwhisperer-target-cw308t` 저장소는 **CW308 UFO baseboard**에 올릴 수 있는
  다수의 타깃 보드 모음을 제공한다.

#### AUTOGLITCH에 주는 의미
- "**Python으로 programmable한 glitch 자동화**" 자체는 이미 선점돼 있다.
- "**다양한 타깃을 교체해가며 실험하는 생태계**"도 이미 존재한다.
- 따라서 AUTOGLITCH는 ChipWhisperer를 무시하고 독자 생태계를 주장하기보다,
  **ChipWhisperer를 하나의 백엔드/어댑터로 흡수할 수 있어야** 한다.

#### 소스
- ChipWhisperer overview: https://chipwhisperer.readthedocs.io/en/v6.0.0b/Capture/overview.html
- ChipWhisperer scope API: https://chipwhisperer.readthedocs.io/en/latest/scope-api.html
- ChipWhisperer tutorials: https://chipwhisperer.readthedocs.io/en/latest/tutorials.html
- chipwhisperer-target-cw308t: https://github.com/newaetech/chipwhisperer-target-cw308t
- ChipWhisperer main repo: https://github.com/newaetech/chipwhisperer

---

### 1.2 재현 가능 scripted glitching: SECGlitcher

#### 확인한 사실
- SEC Consult의 **SECGlitcher**는 STM32 실험을 위해 만든
  **reproducible voltage glitching abstraction layer**다.
- 글에서 명시적으로 **ChipWhisperer 위에 구축**했다고 설명한다.
- 실전 글에는
  - 보드 준비(예: 디커플링 커패시터 제거, 헤더 추가),
  - 외부 전원공급기 사용 예시,
  - 스크립트형 glitch loop
  가 포함된다.
- 즉, 단순 “펄스 쏘기”가 아니라 **재현 가능한 실험 절차 + 실험 스크립트화**까지 이미 시도됐다.

#### AUTOGLITCH에 주는 의미
- "**재현 가능한 STM32 voltage glitching 프레임워크**" 역시 이미 선행 사례가 있다.
- AUTOGLITCH가 차별화되려면, 단순한 loop 자동화가 아니라
  **board-prep metadata / 전원공급기 상태 / wiring 정보 / run bundle**까지
  운영 단위로 묶어야 한다.

#### 소스
- SECGlitcher Part 1: https://sec-consult.com/blog/detail/secglitcher-part-1-reproducible-voltage-glitching-on-stm32-microcontrollers/

---

### 1.3 저가형 / 실험 친화형 glitch 라이브러리: findus / PicoGlitcher

#### 확인한 사실
- `fault-injection-library` 문서는 **findus**를
  microcontroller fault injection용 Python 라이브러리로 소개한다.
- 문서상 지원/연동 예시에는
  - **ChipWhisperer Pro**
  - **ChipWhisperer Husky**
  - **PicoGlitcher**
  가 포함된다.
- PicoGlitcher 문서는 Raspberry Pi Pico 기반 하드웨어로서
  **high-power / low-power MOSFET**, **level shifter**, **target voltage switching** 등
  하드웨어 구성을 설명한다.
- 문서 목차 기준으로 이미
  - **genetic algorithm**
  - **pulse shaping**
  - **multiplexing**
  - **ADC**
  같은 주제가 포함되어 있다.

#### AUTOGLITCH에 주는 의미
- 저비용 hardware + Python automation + 탐색 자동화 역시 이미 존재한다.
- 특히 findus는 "**low-cost hardware + optimizer-like search**"에 가깝다.
- 따라서 AUTOGLITCH는 단순히 BO/RL을 넣는 것으로는 차별화가 약하고,
  **하드웨어 비종속 통합**, **실험 운영성**, **표준화된 결과 스키마**,
  **백엔드 간 공정 비교** 쪽으로 더 밀어야 한다.

#### 소스
- fault-injection-library repo: https://github.com/MKesenheimer/fault-injection-library
- findus docs overview: https://fault-injection-library.readthedocs.io/en/latest/
- PicoGlitcher docs: https://fault-injection-library.readthedocs.io/en/latest/findus/hardware/picoglitcher.html

---

### 1.4 타깃 특화형 소형 프로젝트도 이미 존재

#### A. stm32f1-picopwner
- Pi Pico로 STM32F1 RDP bypass 계열 공격을 구현한 프로젝트다.
- README는 **Obermaier / Schink / Moczek 계열 STM32 glitch + FPB 아이디어**를
  Pico로 재구성한 구현이라고 설명한다.

소스:
- https://github.com/CTXz/stm32f1-picopwner

#### B. C8051F34x_Glitch
- 보호 우회 타깃을 위해
  - proprietary debug protocol 분석,
  - custom debugger 작성,
  - ChipWhisperer notebook 기반 glitching
  을 결합한 프로젝트다.

소스:
- https://github.com/debug-silicon/C8051F34x_Glitch

#### C. FaultyCat / PicoEMP / ChipSHOUTER 계열
- **FaultyCat**은 저비용 EMFI 지향 프로젝트로 소개되며,
  문서상 `ChipSHOUTER PicoEMP` 기반에서 출발해
  **voltage glitching / trigger pins / analog input / JTAG/SWD scanner** 같은 기능을 언급한다.
- `chipshouter-picoemp`는 NewAE의 공개 저장소로,
  EMFI 방향의 실험 접근이 오픈소스 진영에서도 이미 존재함을 보여준다.

소스:
- FaultyCat repo: https://github.com/ElectronicCats/faultycat
- chipshouter-picoemp repo: https://github.com/newaetech/chipshouter-picoemp

#### AUTOGLITCH에 주는 의미
- 타깃 하나를 깊게 파는 **“완결형 PoC”** 는 이미 많다.
- 따라서 AUTOGLITCH는 단일 exploit PoC가 아니라
  **여러 타깃/여러 백엔드에서 같은 절차로 돌릴 수 있는 실험 운영 프레임워크**가 되어야 한다.

---

## 2) 학술 논문 관점의 앵커

### A. 실험 재현성 / 자동화 / 탐색 공간
- Endo et al., **A Configurable On-Chip Glitchy-Clock Generator for Fault Injection Experiments** (2012)  
  https://www.jstage.jst.go.jp/article/transfun/E95.A/1/E95.A_1_263/_article
- Nedospasov et al., **Glitch it if you can** (CARDIS 2013)  
  https://cardis.org/cardis2013/proceedings/CARDIS2013_16.pdf
- Bhasin et al., **SoK: Automated Fault Injection Simulation Frameworks** (2024)  
  https://eprint.iacr.org/2024/1944

### B. 실전 glitching 공격의 수준
- Murdock et al., **One Glitch to Rule Them All** (2021)  
  https://arxiv.org/abs/2108.04575
- Obermaier et al. 계열 STM32 RDP/boot 보안 우회 연구는
  이후 여러 실전 레포(stm32f1-picopwner 등)의 직접적 영감이 되었다.

### C. 다중/정교 glitch 방향
- Coppens et al., **μ-Glitch** (2023)  
  https://arxiv.org/abs/2302.06932

#### AUTOGLITCH에 주는 의미
- 학계에서도 이미
  - 재현성,
  - guided search,
  - 복수 fault,
  - 고가치 타깃 공격
  까지 논의가 진척돼 있다.
- AUTOGLITCH의 novelty를 학술적으로 만들려면
  "**새로운 glitch 물리**"가 아니라
  "**실험 운영/재현성/일반화/primitive mapping/benchmarking**"에서 잡아야 한다.

---

## 3) 우리가 주장하면 안 되는 것

현재 선행작을 보면 AUTOGLITCH는 다음을 주장하면 안 된다.

- "우리가 최초의 programmable fault injection 자동화다"
- "우리가 최초의 reproducible STM32 glitching framework다"
- "우리가 최초의 저가형 Python glitching toolchain이다"
- "우리가 최초로 Jupyter/Python으로 ChipWhisperer 같은 장비를 자동화했다"

대신 아래처럼 포지셔닝해야 한다.

> AUTOGLITCH는 **기존 FI 장비/브리지/PoC를 포괄하는 실험 운영 프레임워크**이며,  
> **하드웨어 비종속성, preflight/queue/soak/RC 운영성, typed report schema, fault-to-primitive 추상화**를
> 핵심 가치로 둔다.

---

## 4) AUTOGLITCH가 차별점을 가지려면 무엇을 해야 하나

### 4.1 ChipWhisperer를 정식 백엔드로 흡수
가장 중요한 차별화 포인트는 "**ChipWhisperer와 경쟁하는 척 하지 말고, 흡수하라**"이다.

#### 해야 할 일
- `hardware/`에 **ChipWhisperer adapter plugin** 추가
- `serial-json-hardware`와 같은 수준으로
  - detect
  - setup
  - doctor
  - preflight
  - run
  - report
  에 연결
- 같은 실험 config가
  - Raspberry Pi bridge
  - ChipWhisperer
  - findus/PicoGlitcher
  에서 공통적으로 돌아가게 만들기

#### 왜 차별화가 되나
- ChipWhisperer는 훌륭하지만 **자기 하드웨어 생태계 중심**이다.
- AUTOGLITCH가 **“CW도 지원하는 상위 control plane”** 이 되면,
  단순 복제품이 아니라 **통합 오케스트레이터**가 된다.

---

### 4.2 findus/PicoGlitcher를 비교 백엔드로 지원

#### 해야 할 일
- findus/PicoGlitcher용 adapter 추가 또는 protocol bridge 작성
- 동일 타깃/동일 목표에서
  - random
  - grid
  - genetic algorithm
  - BO
  - RL
  을 공정 비교

#### 왜 차별화가 되나
- findus는 이미 low-cost glitching + search 아이디어를 갖고 있다.
- AUTOGLITCH는 그 위에
  **backend-neutral experiment comparison framework**를 얹어야 한다.

---

### 4.3 “run bundle”과 “lab evidence pack”을 프로젝트 정체성으로 밀기

#### 해야 할 일
- 각 실험마다 자동 생성:
  - config hash
  - git SHA
  - target metadata
  - board prep note
  - wiring note
  - preflight report
  - campaign summary
  - manifest
  - decision trace
  - scope/logic-analyzer snapshot path
- `validate-hil-rc` 결과를 **artifact bundle**로 묶기

#### 왜 차별화가 되나
- 선행 도구 대부분은 **실험 실행**에는 강하지만,
  **운영 evidence packaging**은 상대적으로 약하다.
- AUTOGLITCH는 여기서 강한 정체성을 만들 수 있다.

---

### 4.4 “fault-to-primitive”를 실제 데이터 모델로 키우기

#### 해야 할 일
- 단순 success/fail 대신
  - `fault_class`
  - `primitive`
  - `execution.status`
  - `response_time`
  - `reset_detected`
  - `error_code`
  를 표준 필드로 유지
- 관측 결과를
  - instruction skip
  - data corruption
  - auth bypass
  - boot bypass
  - faulted-but-non-exploitable
  로 분류

#### 왜 차별화가 되나
- 많은 도구가 glitch parameter search는 하지만,
  **fault semantics를 재사용 가능한 형태로 표준화**하는 부분은 약하다.
- 이 프로젝트는 여기서 논문/데이터셋 가치가 생긴다.

---

### 4.5 “운영성”을 연구 기여로 끌어올리기

#### 해야 할 일
- preflight / doctor / queue / soak / lock / recovery drill을
  단순 유틸이 아니라 **검증된 운영 모델**로 문서화
- 실장비 검증 기준을 표준화:
  - time-to-first-valid-fault
  - infra failure rate
  - reset rate
  - reproducibility across seeds / days / boards
  - operator intervention count

#### 왜 차별화가 되나
- 선행작 상당수는 “성공 PoC”는 보여도,
  **장시간/반복 실험 운용 표준**은 약하다.
- AUTOGLITCH는 “실험을 운영하는 프레임워크”가 될 수 있다.

---

### 4.6 benchmark suite를 공개 자산으로 만들기

#### 해야 할 일
- 최소 2개 하드웨어 백엔드:
  - Raspberry Pi bridge
  - ChipWhisperer 또는 findus/PicoGlitcher
- 최소 2개 타깃:
  - STM32F3
  - STM32F1 또는 ESP32 계열
- 최소 3개 태스크:
  - glitch detectability benchmark
  - reset/boot perturbation benchmark
  - secure-check bypass benchmark

#### 왜 차별화가 되나
- 단일 레포/단일 블로그 성공 사례보다
  **표준 benchmark + 공통 report schema**가 더 장기적인 가치가 있다.

---

### 4.7 결국 “실장비 증거”가 필요

AUTOGLITCH의 가장 큰 약점은 현재도 동일하다.

- 소프트웨어 구조는 좋음
- 하지만 **field-proven HIL evidence가 부족함**

따라서 차별화 전략의 마지막은 반드시 다음이어야 한다.

#### 최소 실증 기준
1. Raspberry Pi bridge 실증 1세트
2. ChipWhisperer 또는 findus 실증 1세트
3. 타깃 2종 이상
4. run bundle + wiring/photo + artifact 공개
5. 동일 benchmark를 seed/board/day 바꿔 반복

이게 있어야 "**우리는 운영 프레임워크다**"라는 주장이 설득력을 갖는다.

---

## 5) 권장 실행 우선순위

### P0
- ChipWhisperer adapter 설계
- 실장비 evidence pack 1세트 생성
- benchmark schema 초안 작성

### P1
- findus/PicoGlitcher backend 비교
- artifact bundle 자동 생성
- board prep / wiring metadata 스키마화

### P2
- optimizer 비교 실험(random/grid/GA/BO/RL)
- fault-to-primitive 데이터셋 정리
- benchmark report 공개

---

## 6) 현재 시점의 포지셔닝 문장(권장)

> AUTOGLITCH는 fault injection 자체를 발명한 도구가 아니라,  
> **기존 glitching/EMFI/target-specific PoC를 공통 실험 절차로 감싸는 하드웨어 비종속 운영 프레임워크**다.  
> 차별점은 **백엔드 통합, preflight/queue/soak/RC 운영성, typed result schema, fault-to-primitive 분석, reproducibility bundle**에 있다.
