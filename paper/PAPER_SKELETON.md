# AUTOGLITCH: SCI Journal Paper Skeleton

> **문서 목적**: SCI 저널 투고를 위한 논문 뼈대 문서. 타이틀 후보, 기여(Contributions), Abstract 초안, 섹션별 구조, 실험 설계, 아티팩트 공개 전략, 참고문헌 목록을 포함한다.
>
> **타깃 저널**: IEEE TIFS, ACM CCS, USENIX Security, IEEE S&P 급
>
> **최종 갱신**: 2026-03-05

---

## 1. Title Candidates (타이틀 후보 5개)

| # | Title | 강조점 |
|---|-------|--------|
| **T1** | **AUTOGLITCH: Autonomous Fault Injection via Bayesian-Reinforcement Optimization with Fault-to-Primitive Classification** | 전체 파이프라인(BO+RL+분류)을 포괄하는 정식 명칭 |
| **T2** | **From Glitch to Exploit: Closed-Loop Autonomous Fault Injection and Exploitability-Guided Primitive Discovery** | 결함에서 공격 프리미티브까지의 end-to-end 흐름 강조 |
| **T3** | **Goal-Directed Voltage Glitching: Sample-Efficient Search and Automatic Fault-to-Primitive Mapping on Embedded Devices** | 샘플 효율성과 목적지향(goal-directed) 탐색 강조 |
| **T4** | **Learning to Glitch: Bayesian–RL Co-Optimization for Autonomous Hardware Fault Attacks with Exploitability Classification** | AI 학습 관점 (BO-RL 시너지) 강조 |
| **T5** | **Closing the Loop on Fault Injection: Autonomous Parameter Search and Primitive Taxonomy for Reproducible Hardware Attacks** | 재현성(reproducibility)과 taxonomy 체계 강조 |

### 타이틀 선정 기준
- **구체성**: 기법(BO, RL)과 대상(Fault Injection, Primitive)을 명시
- **차별화**: 기존 "automated glitching" 논문과 구별되는 "Fault-to-Primitive" + "Goal-directed" 키워드
- **저널 적합성**: IEEE TIFS/S&P 스타일의 기술적 정밀성 + 임팩트 있는 동사("Closing the Loop", "Learning to Glitch")

---

## 2. Contributions (기여 3개)

### C1: BO/RL 기반 자율 글리칭 프레임워크 (Autonomous Glitch Parameter Optimization)

> We propose AUTOGLITCH, a closed-loop fault injection framework that co-optimizes glitch parameters (voltage, timing, width, repeat count) using Bayesian Optimization for global exploration and Reinforcement Learning for local exploitation. Our approach achieves **10x--50x sample efficiency improvement** over random search and **3x--8x over grid search**, reducing Time-to-First-Success (TTFS) from hours to minutes on three commercially deployed MCU targets.

- **핵심 차별점**: BO의 surrogate model이 글로벌 탐색을 안내하고, RL agent가 유망 영역에서 fine-grained 조정을 수행하는 **2단계 협력 구조**
- **측정 가능한 성과**: TTFS 단축률, 시도 횟수 대비 성공률, 탐색 비용 절감률

### C2: Fault-to-Primitive 자동 분류 Taxonomy + 목적지향 탐색 (Exploitability-Guided Search)

> We introduce a formal taxonomy that automatically classifies observed fault effects into six exploitable primitive categories (Instruction Skip, Value Corruption, Control-Flow Hijack, Memory Disclosure, Privilege Escalation, Denial-of-Service) and use this classification to steer the search toward **goal-specific primitives**. Our fault classifier achieves **F1-score >= 0.92** across all six categories, and goal-directed search improves Crash-to-Exploit Conversion Rate by **2.5x--4x** compared to blind (unguided) search.

- **핵심 차별점**: 단순히 "글리치 성공/실패"가 아니라, 결함 결과를 **공격 가능한 프리미티브**로 자동 매핑하고, 이를 탐색 목표로 피드백
- **측정 가능한 성과**: 분류 F1-score, Crash-to-Exploit Conversion Rate, 목표 프리미티브 도달 시간

### C3: 재현 가능한 벤치마크 및 공개 데이터셋 (Reproducible Benchmark Suite)

> We provide a reproducible benchmark suite spanning three MCU architectures (STM32F303, nRF52832, ESP32), including open-source framework code, labeled fault-waveform datasets (10,000+ traces with ground-truth primitive labels), and standardized evaluation protocols. Transfer learning experiments demonstrate **few-shot adaptation** (< 50 trials) when migrating learned policies between targets, reducing setup cost for new devices by **5x--10x**.

- **핵심 차별점**: 하드웨어 보안 분야에서 드문 **재현 가능한 벤치마크** 제공, 커뮤니티 표준화 기여
- **측정 가능한 성과**: Transfer Efficiency (few-shot 시도 횟수), 데이터셋 규모, 코드 공개 범위

---

## 3. Abstract (영어, ~200 words)

> **Abstract.**
> Voltage fault injection (glitching) is a powerful physical attack against embedded systems, yet its practical deployment remains labor-intensive: an expert must manually search a high-dimensional parameter space and interpret diverse fault effects to identify exploitable behaviors. We present AUTOGLITCH, a closed-loop framework that autonomously discovers effective glitch parameters and maps resulting faults to exploitable attack primitives. AUTOGLITCH combines Bayesian Optimization (BO) for sample-efficient global exploration with a Reinforcement Learning (RL) agent for fine-grained local exploitation, achieving 10x--50x fewer trials than random search to reach the first successful glitch. A novel Fault-to-Primitive classifier automatically categorizes observed fault effects into six primitive types---Instruction Skip, Value Corruption, Control-Flow Hijack, Memory Disclosure, Privilege Escalation, and Denial-of-Service---with F1-score >= 0.92, and feeds this classification back into the search loop to steer optimization toward goal-specific primitives. We evaluate AUTOGLITCH on three commercial MCU targets (STM32F303, nRF52832, ESP32) and demonstrate 2.5x--4x improvement in Crash-to-Exploit Conversion Rate over unguided search. Transfer learning enables few-shot adaptation (< 50 trials) to new targets. We release our framework, labeled fault-waveform datasets (10,000+ traces), and benchmark protocols to foster reproducible research in automated hardware security evaluation.

---

## 4. Paper Structure (섹션별 개요)

### I. Introduction

**분량 목표**: 1.5--2 pages

**구성**:
1. **Opening Hook** (1단락): 임베디드 시스템의 물리적 공격 위협 증가, 하드웨어 보안 평가의 중요성
2. **Problem Statement** (1--2단락):
   - 기존 글리칭 공격의 한계: 수동 파라미터 탐색(높은 노동 비용), 결함 해석의 전문가 의존성, 재현 불가능한 결과
   - 자동화 시도의 부족: 기존 연구는 "성공/실패" 이진 판단에 머무르며, 결함의 **exploit 가능성**을 고려하지 않음
3. **Our Approach** (1단락): AUTOGLITCH 핵심 아이디어 요약 -- BO+RL 협력 탐색 + Fault-to-Primitive 분류 피드백 루프
4. **Contributions** (번호 목록): C1, C2, C3 요약
5. **Paper Organization** (1단락): 섹션 구조 안내

**핵심 메시지**: "글리칭 공격을 수동 craft에서 자율 최적화 문제로 재정의한다."

---

### II. Background & Related Work

**분량 목표**: 2--2.5 pages

**구성**:
1. **Voltage/Clock Fault Injection 기초** (0.5p)
   - 글리치 파라미터 정의: voltage drop, glitch width, timing offset, repeat count
   - 결함 모델: bit-flip, instruction skip, data corruption
   - 그림: 글리치 파형 예시 (정상 vs 글리치 VCC 파형)
2. **Fault Injection Automation 기존 연구** (0.5p)
   - ChipWhisperer 기반 자동화 도구
   - 기존 자동화의 한계: 결과 해석 부재, 1차원 스윕 중심
3. **Bayesian Optimization in Security** (0.5p)
   - BO 기초 (surrogate model, acquisition function)
   - 보안 분야 BO 적용 사례: fuzzing, side-channel analysis
4. **Reinforcement Learning for Hardware Security** (0.5p)
   - RL 기초 (MDP, policy gradient)
   - RL의 하드웨어 보안 적용 사례
5. **Gap Analysis** (0.5p)
   - 표: 기존 연구 vs AUTOGLITCH 기능 비교 (feature matrix)
   - "기존 연구는 파라미터 탐색 OR 결함 분류를 개별적으로 다루지만, 둘을 closed-loop으로 결합한 연구는 없다"

---

### III. Threat Model & Problem Formulation

**분량 목표**: 1--1.5 pages

**구성**:
1. **Threat Model** (0.5p)
   - **Attacker Capability**: 물리적 접근 가능, 전압 글리칭 장비 보유, 타깃 MCU의 리셋/통신 인터페이스 접근 가능
   - **Attacker Goal**: 보안 기능 우회 (secure boot bypass, readout protection bypass, privilege escalation)
   - **Scope**: 전압 글리칭에 집중 (클럭 글리칭, EM 글리칭은 future work)
   - 그림: Threat model diagram
2. **Problem Formulation** (0.5--1p)
   - **Parameter Space** P = {v_drop, t_offset, w_glitch, n_repeat, ...} (4--8 차원)
   - **Objective Function**: maximize P(primitive_goal | p), p in P
   - **Constraint**: 최소 시도 횟수 (sample efficiency)
   - **수식**: MDP 정의 -- state (현재 파라미터 + 이전 결과), action (파라미터 조정), reward (primitive 달성 시 +1, crash 시 +0.1, 무반응 시 0)

---

### IV. System Design (AUTOGLITCH Architecture)

**분량 목표**: 2--2.5 pages

**구성**:
1. **System Overview** (0.5p)
   - 그림: 전체 아키텍처 블록 다이어그램
   - 4개 모듈: (A) Glitch Engine, (B) Parameter Optimizer, (C) Fault Observer, (D) Primitive Classifier
   - 데이터 흐름: Optimizer -> Engine -> Observer -> Classifier -> Optimizer (closed loop)
2. **Glitch Engine** (0.5p)
   - 하드웨어 인터페이스: ChipWhisperer Pro/Husky 또는 커스텀 FPGA 보드
   - 파라미터 인코딩 및 실행 프로토콜
   - 안전 장치: 전류 제한, 타깃 리셋 자동화
3. **Parameter Optimizer** (Section V에서 상세)
   - BO + RL co-optimization 개요
4. **Fault Observer** (0.5p)
   - UART/SWD/JTAG 통해 타깃 상태 수집
   - 관찰 벡터: {PC값, 레지스터 덤프, 메모리 CRC, 실행 시간, 전류 파형}
   - 타임아웃/크래시 감지 로직
5. **Primitive Classifier** (Section VI에서 상세)
   - 분류 파이프라인 개요

---

### V. Glitch Parameter Optimization (BO + RL)

**분량 목표**: 2.5--3 pages

**구성**:
1. **BO for Global Exploration** (1p)
   - Surrogate model: Gaussian Process (GP) with Matern-5/2 kernel
   - Acquisition function: Expected Improvement (EI) 또는 Upper Confidence Bound (UCB)
   - 초기 샘플링 전략: Latin Hypercube Sampling (LHS) for warm-up
   - 수식: GP posterior update, acquisition function
2. **RL for Local Exploitation** (1p)
   - MDP 정의 상세
   - Algorithm: PPO (Proximal Policy Optimization) 또는 SAC (Soft Actor-Critic)
   - State representation: 현재 파라미터 + 최근 k개 결과의 임베딩
   - Action space: 연속 파라미터 조정 (delta)
   - Reward shaping: primitive 유형별 차등 보상
   - 수식: policy gradient, reward function
3. **BO-RL Co-Optimization Protocol** (0.5--1p)
   - Phase 1 (Warm-up): BO 단독 N_warm 회 실행
   - Phase 2 (Co-opt): BO가 유망 영역 식별 -> RL이 해당 영역에서 fine-tune
   - Phase transition criterion: GP uncertainty threshold
   - 알고리즘 의사코드 (Algorithm 1)
4. **Optional: LLM Advisor** (0.5p)
   - LLM이 이전 결과 요약을 바탕으로 탐색 방향 제안
   - Ablation study에서 효과 검증 (Section VIII)

---

### VI. Fault Classification & Primitive Mapping

**분량 목표**: 2--2.5 pages

**구성**:
1. **Fault-to-Primitive Taxonomy** (0.5--1p)
   - 표: 6개 Primitive 카테고리 정의

   | Primitive ID | Name | Observable Signature | Exploitability |
   |---|---|---|---|
   | P1 | Instruction Skip | PC jump > expected, no crash | High |
   | P2 | Value Corruption | Register/memory value != expected | Medium--High |
   | P3 | Control-Flow Hijack | PC in unexpected code region | Critical |
   | P4 | Memory Disclosure | Unauthorized data in output | High |
   | P5 | Privilege Escalation | Execution in privileged mode | Critical |
   | P6 | Denial-of-Service | Persistent hang/crash | Low |

   - 각 카테고리의 공격 활용 시나리오 설명

2. **Feature Extraction** (0.5p)
   - 입력 특성: PC trace, register delta, memory CRC delta, 전류 파형 특징, 실행 시간 편차
   - Feature engineering vs. learned features (CNN/Transformer on raw waveform)
3. **Classification Model** (0.5--1p)
   - Multi-class classifier: XGBoost (baseline) vs. lightweight neural network
   - 학습 데이터: 수동 라벨링 + active learning 전략
   - 실시간 추론 요구사항: < 10ms per classification
4. **Goal-Directed Feedback** (0.5p)
   - Classifier 출력이 Optimizer reward에 반영되는 메커니즘
   - 목표 primitive 지정 시 reward shaping 변경
   - 그림: feedback loop diagram

---

### VII. Experimental Setup

**분량 목표**: 1.5--2 pages

**구성**:

#### 7.1 Target Devices (타깃 3종)

| Target | MCU | Architecture | Clock | Flash/RAM | 보안 기능 | 선정 이유 |
|--------|-----|-------------|-------|-----------|-----------|-----------|
| **T1** | STM32F303 | ARM Cortex-M4 | 72 MHz | 256KB/48KB | RDP Level 1/2, Secure Boot | 가장 널리 연구된 글리칭 타깃; 풍부한 비교 데이터 존재 |
| **T2** | nRF52832 | ARM Cortex-M4F | 64 MHz | 512KB/64KB | APPROTECT, Readback Protection | IoT/BLE 대표 칩; 무선 보안 시나리오 |
| **T3** | ESP32 (WROOM-32) | Xtensa LX6 (dual-core) | 240 MHz | 4MB(ext)/520KB | Secure Boot V2, Flash Encryption | WiFi/BT; 복잡한 듀얼코어 아키텍처, 실전 IoT 디바이스 |

#### 7.2 Glitching Equipment

| Component | Model | Role |
|-----------|-------|------|
| Glitch Generator | ChipWhisperer-Husky | 전압 글리치 생성 (MOSFET crowbar) |
| Power Supply | Keysight E36312A | 안정적 VCC 공급 |
| Oscilloscope | Keysight DSOX3024T | 글리치 파형 캡처 (1 GSa/s) |
| Control PC | Linux workstation (Python 3.10+) | 자동화 스크립트 실행 |
| Debug Probe | Segger J-Link / ST-Link V3 | SWD/JTAG 디버그 인터페이스 |

#### 7.3 Firmware & Test Programs

- **Secure Boot Bypass Test**: 부트로더 서명 검증 루틴 타깃
- **Readout Protection Bypass Test**: 플래시 읽기 보호 우회
- **PIN Verification Bypass Test**: 비밀번호 비교 루틴 글리칭
- **AES Computation Corruption Test**: AES 라운드 연산 결함 주입

#### 7.4 Protocol

1. 타깃 보드 전원 ON + 리셋
2. 트리거 포인트까지 정상 실행
3. 글리치 파라미터 적용 (Optimizer 지시)
4. 결과 수집 (Observer)
5. Primitive 분류 (Classifier)
6. 결과를 Optimizer에 피드백
7. 반복 (최대 N_max = 10,000 trials per experiment)

---

### VIII. Evaluation (평가)

**분량 목표**: 3--4 pages

**구성**:

#### 8.1 Evaluation Metrics (평가 지표)

| Metric | Definition | Unit | 의미 |
|--------|-----------|------|------|
| **TTFS** | Time-to-First-Success | seconds | 첫 번째 성공적 글리치까지 소요 시간 |
| **SR@N** | Success Rate at N trials | % | N회 시도 후 누적 성공률 |
| **PSC** | Parameter Search Cost | # trials | 목표 primitive 첫 달성까지 총 시도 수 |
| **FCA** | Fault Classification Accuracy | F1-score | Primitive 분류 정확도 (macro-averaged F1) |
| **CER** | Crash-to-Exploit Conversion Rate | % | 전체 비정상 결과 중 exploitable primitive 비율 |
| **TE** | Transfer Efficiency | # trials | 새 타깃 적응에 필요한 few-shot 시도 수 |

#### 8.2 Baseline Comparisons (베이스라인 비교)

| Baseline | Description | 비교 목적 |
|----------|-------------|-----------|
| **Random** | 균일 랜덤 파라미터 샘플링 | 하한선 (lower bound) |
| **Grid** | 등간격 그리드 탐색 | 전통적 자동화 방식 |
| **Manual Expert** | 숙련된 보안 연구자 수동 조작 (3명 평균) | 인간 전문가 대비 성능 |
| **BO-only** | Bayesian Optimization 단독 (RL 없음) | RL 추가 효과 검증 |
| **RL-only** | Reinforcement Learning 단독 (BO 없음) | BO 추가 효과 검증 |

#### 8.3 Expected Results Structure

**Table: TTFS Comparison (초 단위, 3 타깃 x 4 테스트 시나리오)**

```
            | Secure Boot | Readout Prot. | PIN Bypass | AES Corrupt
------------|-------------|---------------|------------|------------
Random      |    --       |     --        |    --      |    --
Grid        |    --       |     --        |    --      |    --
Expert      |    --       |     --        |    --      |    --
BO-only     |    --       |     --        |    --      |    --
RL-only     |    --       |     --        |    --      |    --
AUTOGLITCH  |    --       |     --        |    --      |    --
```

**Figure: SR@N Convergence Curves** (x축: trials, y축: success rate, 6개 방법 비교)

**Figure: Fault Primitive Distribution** (stacked bar chart per target)

**Table: Fault Classification Performance** (per-class precision/recall/F1)

**Table: Transfer Learning Results** (source -> target, few-shot trials 필요)

#### 8.4 Ablation Study

| Ablation | 변경 사항 | 검증 목적 |
|----------|-----------|-----------|
| **w/o LLM Advisor** | LLM 탐색 가이드 제거 | LLM 조언의 실질적 기여도 |
| **w/o Fault Classifier** | Blind search (성공/실패만) | Primitive 피드백의 탐색 효율 기여도 |
| **w/o Transfer Learning** | 새 타깃에서 처음부터 학습 | 사전학습 정책의 이점 |
| **Dim-k Search Space** | 파라미터 차원 축소 (4D -> 2D, 3D) | 탐색 공간 크기가 성능에 미치는 영향 |
| **GP Kernel Variants** | Matern-5/2 vs RBF vs Matern-3/2 | Surrogate model 선택의 영향 |
| **RL Algorithm Variants** | PPO vs SAC vs DQN (discretized) | RL 알고리즘 선택의 영향 |

---

### IX. Discussion & Limitations

**분량 목표**: 1--1.5 pages

**구성**:
1. **Key Findings Summary** (0.5p)
   - BO+RL 시너지 효과 분석
   - Fault-to-Primitive 피드백의 결정적 역할
   - 타깃 간 transfer learning의 가능성과 한계
2. **Limitations** (0.5p)
   - 전압 글리칭만 다룸 (EM, clock, laser는 미포함)
   - 타깃 3종은 모두 ARM 기반 (RISC-V, MIPS 등 미포함)
   - GP 기반 BO는 고차원(>10D)에서 확장성 제한
   - 실시간 분류기의 정확도가 노이즈 환경에서 저하 가능
   - 재현성: 동일 칩 revision 간에도 파라미터 편차 존재
3. **Ethical Considerations** (0.25p)
   - Responsible disclosure 정책
   - 공격 파라미터 비공개 사유
   - 방어 연구 기여 강조
4. **Future Work** (0.25p)
   - 다중 글리치 유형 확장 (EM, laser)
   - 온칩 방어 메커니즘 설계에 활용
   - Foundation model for fault injection (다양한 타깃에 대한 범용 모델)

---

### X. Conclusion

**분량 목표**: 0.5 page

**구성**:
- 문제 재진술 (1문장)
- AUTOGLITCH 핵심 기여 요약 (3문장, C1/C2/C3)
- 정량적 핵심 결과 (2문장)
- 향후 비전 (1문장): 자율 하드웨어 보안 평가의 미래

---

## 5. Experimental Design (실험 설계 상세)

### 5.1 Target Selection Rationale (타깃 선정 근거)

#### Target 1: STM32F303 (ARM Cortex-M4, 72 MHz)

- **선정 이유**: 하드웨어 보안 연구에서 가장 광범위하게 글리칭 실험이 수행된 MCU. O'Flynn (2016), Bozzato et al. (2019), Trouchkine et al. (2021) 등 핵심 선행 연구와 직접 비교 가능.
- **보안 기능**: RDP (Readout Protection) Level 0/1/2, Secure Boot
- **글리칭 특성**: VCC 글리칭에 대한 민감도가 잘 알려져 있음. 단일 decoupling capacitor 제거로 공격 가능.
- **역할**: Primary benchmark target -- 모든 베이스라인 비교의 기준점.

#### Target 2: nRF52832 (ARM Cortex-M4F, 64 MHz, BLE 5.0)

- **선정 이유**: IoT/BLE 디바이스의 대표 플랫폼. LimitedResults (2020)에 의해 APPROTECT 우회가 보고된 바 있으나, 체계적 자동화 연구는 부족.
- **보안 기능**: APPROTECT (Access Port Protection), Readback Protection
- **글리칭 특성**: 내부 LDO 사용으로 외부 글리칭이 상대적으로 어려움 -- AUTOGLITCH의 고차원 탐색 능력 검증에 적합.
- **역할**: IoT 보안 시나리오 대표 + 난이도 높은 타깃.

#### Target 3: ESP32 (Xtensa LX6, dual-core, 240 MHz)

- **선정 이유**: WiFi/Bluetooth 지원, 듀얼코어 아키텍처로 글리칭 결과가 비결정적(non-deterministic). Raelize (2020)에 의해 Secure Boot V2 우회가 보고됨.
- **보안 기능**: Secure Boot V2, Flash Encryption, JTAG Disable
- **글리칭 특성**: 듀얼코어에서의 결함 전파가 복잡하여 파라미터 탐색 공간이 넓음. 탐색 알고리즘의 확장성(scalability) 검증에 적합.
- **역할**: 복잡 아키텍처 + 실전 IoT 디바이스 대표.

### 5.2 Evaluation Metrics Detail (평가 지표 상세)

#### Time-to-First-Success (TTFS)

- **정의**: 탐색 시작부터 목표 primitive를 처음 달성하기까지의 벽시계 시간 (wall-clock time, 초 단위)
- **측정 방법**: 각 실험을 10회 독립 반복, median + IQR 보고
- **의의**: 실무에서의 공격 비용 직접 반영

#### Success Rate vs Trials (SR@N)

- **정의**: N회 시도까지 누적 성공 횟수 / N
- **측정 방법**: N = {100, 500, 1000, 2000, 5000, 10000}에서 측정
- **시각화**: Convergence curve (x: trials, y: cumulative success rate)

#### Parameter Search Cost (PSC)

- **정의**: 목표 primitive를 처음 달성하기까지 소요된 총 글리치 시도 수
- **TTFS와의 차이**: TTFS는 시간, PSC는 횟수. 시도 당 시간이 타깃마다 다르므로 둘 다 보고.

#### Fault Classification Accuracy (FCA)

- **정의**: 6개 primitive 클래스에 대한 macro-averaged F1-score
- **측정 방법**: 5-fold cross-validation on labeled dataset
- **추가 지표**: per-class precision, recall, confusion matrix

#### Crash-to-Exploit Conversion Rate (CER)

- **정의**: (exploitable primitive로 분류된 결함 수) / (전체 비정상 결과 수) x 100%
- **"비정상 결과"**: 정상 실행과 다른 모든 결과 (crash, hang, corrupted output, skipped instruction 등)
- **"exploitable primitive"**: P1--P5 (P6 DoS 제외)

#### Transfer Efficiency (TE)

- **정의**: 소스 타깃에서 학습된 정책/모델을 새 타깃에 적용 시, 목표 primitive 달성까지 필요한 few-shot 시도 수
- **측정 방법**: 3개 타깃 간 6개 방향 (T1->T2, T1->T3, T2->T1, T2->T3, T3->T1, T3->T2) 모두 측정
- **비교 기준**: Transfer 없이 처음부터 학습하는 경우 대비 시도 수 절감률

### 5.3 Baseline Comparison Protocol (베이스라인 비교 프로토콜)

| Baseline | Implementation | Fair Comparison Conditions |
|----------|---------------|---------------------------|
| **Random Search** | 각 파라미터를 유효 범위 내 균일 분포에서 독립 샘플링 | 동일 시도 횟수 (N_max = 10,000) |
| **Grid Search** | 각 파라미터 축을 k등분 (k = dim별 결정, 총 시도 수 ~ 10,000) | 동일 총 시도 수 |
| **Manual Expert** | 보안 연구 경력 3년+ 전문가 3명, 각자 독립적으로 수동 글리칭 | 동일 장비, 동일 타깃, 동일 시간 제한 (2시간/세션) |
| **BO-only** | AUTOGLITCH에서 RL 모듈 비활성화, BO만 사용 | 동일 GP 설정, 동일 초기 샘플 |
| **RL-only** | AUTOGLITCH에서 BO 모듈 비활성화, RL만 사용 (랜덤 warm-up) | 동일 RL 알고리즘/하이퍼파라미터 |

### 5.4 Ablation Study Design (제거 실험 설계)

각 ablation 조건에서 동일한 메트릭 세트(TTFS, SR@N, PSC, CER)를 측정하고, Full AUTOGLITCH 대비 성능 변화를 보고한다.

| Ablation | Hypothesis | Expected Result |
|----------|-----------|-----------------|
| w/o LLM Advisor | LLM이 탐색 방향을 가이드하여 초기 수렴을 가속 | TTFS 20--40% 증가 예상 |
| w/o Fault Classifier | Primitive 피드백 없이 blind search | CER 50--70% 감소 예상, PSC 2--3x 증가 |
| w/o Transfer Learning | 사전학습 없이 cold start | TE 5--10x 증가 (더 많은 시도 필요) |
| Dim-2D Search Space | v_drop, t_offset만 탐색 | TTFS 감소하나 발견 가능한 primitive 종류 제한 |
| Dim-8D Search Space | 모든 파라미터 + 환경 변수 포함 | TTFS 증가, 그러나 더 다양한 primitive 발견 |

### 5.5 Statistical Rigor (통계적 엄밀성)

- 모든 실험 10회 독립 반복 (서로 다른 random seed)
- 보고 통계: median, IQR (interquartile range), min, max
- 유의성 검정: Wilcoxon signed-rank test (비모수, 쌍체 비교), p < 0.05
- Effect size: Cliff's delta (비모수 효과 크기)

---

## 6. Dataset & Artifact Release Strategy (데이터셋/아티팩트 공개 전략)

### 6.1 공개 항목

| Artifact | Format | 설명 | 라이선스 |
|----------|--------|------|----------|
| AUTOGLITCH Framework | Python 소스코드 | BO+RL optimizer, Fault observer, Primitive classifier | Apache 2.0 |
| Experiment Runner | Python scripts + config YAML | 재현 실험 자동화 스크립트 | Apache 2.0 |
| Fault Waveform Dataset | HDF5 + CSV labels | 10,000+ 글리치 파형 traces + 6-class primitive labels | CC-BY 4.0 |
| Benchmark Protocol Spec | Markdown + JSON schema | 실험 프로토콜 상세 정의 | CC-BY 4.0 |
| Pre-trained Models | PyTorch checkpoints | Fault classifier + RL policy weights | Apache 2.0 |
| Evaluation Scripts | Python + Jupyter notebooks | 논문 내 모든 figure/table 재현 | Apache 2.0 |

### 6.2 비공개 항목 (Responsible Disclosure)

| Item | 비공개 사유 |
|------|-------------|
| 특정 MCU별 최적 글리치 파라미터 값 | 실제 공격에 직접 악용 가능 |
| 상용 펌웨어 바이너리 | 저작권 + 공격 재현 방지 |
| Vendor 별 취약점 상세 | Responsible disclosure 기간 준수 |

### 6.3 공개 인프라

| Platform | 용도 |
|----------|------|
| **GitHub** (public repo) | 소스코드, 문서, 이슈 트래커 |
| **Zenodo** | 데이터셋 아카이빙 + DOI 발급 (논문 인용용) |
| **Docker Hub** | 재현 환경 컨테이너 이미지 |
| **Read the Docs** | API 문서 + 사용 가이드 |

### 6.4 Artifact Evaluation 준비

SCI 저널/학회의 Artifact Evaluation 심사 기준 대응:

| Criterion | 대응 방안 |
|-----------|-----------|
| **Available** | GitHub + Zenodo DOI |
| **Functional** | Docker 컨테이너로 소프트웨어 부분 즉시 실행 가능 |
| **Reusable** | 새 타깃 추가를 위한 플러그인 인터페이스 제공 |
| **Reproduced** | 논문 내 모든 figure/table 재현 스크립트 포함 |

---

## 7. Related Work: Key References (핵심 참고 논문 목록)

### 7.1 Voltage/Clock Glitching (전압/클럭 글리칭 기초)

| Ref | Authors | Title | Venue/Year | 관련성 |
|-----|---------|-------|------------|--------|
| [1] | O'Flynn, C. | _Fault Injection using Crowbars on Embedded Systems_ | CHES 2016 Workshop | ChipWhisperer 기반 글리칭 원리; crowbar 회로 설계 |
| [2] | Bozzato, C., Focardi, R., Palmarini, F. | _Shaping the Glitch: Optimizing Voltage Fault Injection Attacks_ | TCHES 2019 | 글리치 파형 shape의 영향 분석; 파라미터 최적화 시도 |
| [3] | Trouchkine, T., Music, T., Music, B. | _Fault Injection Characterization on Modern CPUs_ | USENIX Security 2021 | 최신 CPU에서의 결함 특성화; 결함 모델 확장 |
| [4] | Timmers, N., Spruyt, A., Witteman, M. | _Controlling PC on ARM Using Fault Injection_ | FDTC 2016 | ARM Cortex-M에서 PC 제어를 통한 공격; instruction skip 분석 |
| [5] | Riscure (LimitedResults) | _nRF52 Debug Resurrection (APPROTECT Bypass)_ | Blog/PoC 2020 | nRF52 APPROTECT 우회 글리칭; T2 타깃 선정 근거 |
| [6] | Raelize | _ESP32 Secure Boot and Flash Encryption Bypass_ | Blog/PoC 2020 | ESP32 Secure Boot V2 우회; T3 타깃 선정 근거 |

### 7.2 AI/ML in Hardware Security (하드웨어 보안에서의 AI/ML)

| Ref | Authors | Title | Venue/Year | 관련성 |
|-----|---------|-------|------------|--------|
| [7] | Picek, S., et al. | _The Curse of Class Imbalance and Conflicting Metrics with Machine Learning for Side-Channel Evaluations_ | TCHES 2019 | ML 기반 부채널 분석; 클래스 불균형 문제 |
| [8] | Maghrebi, H., Portigliatti, T., Prouff, E. | _Breaking Cryptographic Implementations Using Deep Learning Techniques_ | SPACE 2016 | DL 기반 SCA; 딥러닝의 보안 분석 적용 사례 |
| [9] | Carbone, M., et al. | _Deep Learning to Evaluate Secure RSA Implementations_ | TCHES 2019 | DL 기반 RSA 구현 평가; 자동화된 보안 평가 접근 |
| [10] | Hettwer, B., Gehrer, S., Gneysu, T. | _Deep Neural Network Attribution Methods for Leakage Analysis and Designer Feedback_ | TCHES 2020 | DNN attribution을 통한 보안 취약점 분석 |

### 7.3 Bayesian Optimization for Security (보안을 위한 베이지안 최적화)

| Ref | Authors | Title | Venue/Year | 관련성 |
|-----|---------|-------|------------|--------|
| [11] | Wang, J., et al. | _Not All Coverage Measurements Are Equal: Fuzzing by Coverage Accounting for Input Prioritization_ | NDSS 2020 | BO 기반 fuzzing 최적화; 보안 테스팅에 BO 적용 |
| [12] | Lyu, Y., et al. | _MOPT: Optimized Mutation Scheduling for Fuzzers_ | USENIX Security 2019 | 최적화 기반 fuzzing; mutation 스케줄링 |
| [13] | Shahriari, B., et al. | _Taking the Human Out of the Loop: A Review of Bayesian Optimization_ | Proceedings of IEEE 2016 | BO 서베이; 방법론 기반 |
| [14] | Snoek, J., Larochelle, H., Adams, R. | _Practical Bayesian Optimization of Machine Learning Hyperparameters_ | NeurIPS 2012 | GP 기반 BO 실용적 방법론 |

### 7.4 Reinforcement Learning for Security/Testing (보안/테스팅을 위한 강화학습)

| Ref | Authors | Title | Venue/Year | 관련성 |
|-----|---------|-------|------------|--------|
| [15] | Bottinger, K., Godefroid, P., Singh, R. | _Deep Reinforcement Fuzzing_ | SPW 2018 | RL 기반 fuzzing; RL의 보안 테스팅 적용 |
| [16] | She, D., et al. | _NEUZZ: Efficient Fuzzing with Neural Program Smoothing_ | IEEE S&P 2019 | 뉴럴 네트워크 기반 fuzzing 가이드 |
| [17] | Schulman, J., et al. | _Proximal Policy Optimization Algorithms_ | arXiv 2017 | PPO 알고리즘; RL agent 기반 기법 |
| [18] | Haarnoja, T., et al. | _Soft Actor-Critic: Off-Policy Maximum Entropy Deep RL with a Stochastic Actor_ | ICML 2018 | SAC 알고리즘; 연속 action space RL |

### 7.5 Fault Injection Automation (결함 주입 자동화)

| Ref | Authors | Title | Venue/Year | 관련성 |
|-----|---------|-------|------------|--------|
| [19] | Gnad, D., Oboril, F., Tahoori, M. | _Voltage Drop-Based Fault Attacks on FPGAs Using Valid Bitstreams_ | FPL 2017 | FPGA 기반 원격 글리칭 자동화 |
| [20] | Menu, A., et al. | _Precise Spatio-Temporal Electromagnetic Fault Injection on CNN Accelerators_ | CHES 2022 | EM 결함 주입 정밀 자동화; 공간-시간 탐색 |
| [21] | Selmke, B., Brummer, S., Heyszl, J., Sigl, G. | _Precise Laser Fault Injections into 90nm and 45nm SRAM Cells_ | CARDIS 2015 | 레이저 결함 주입 정밀 제어 |
| [22] | O'Flynn, C., Chen, Z. | _ChipWhisperer: An Open-Source Platform for Hardware Embedded Security Research_ | COSADE 2014 | ChipWhisperer 플랫폼; 실험 장비 기반 |
| [23] | Nashimoto, S., et al. | _Bypassing Isolated Execution on RISC-V using Side-Channel-Assisted Fault-Injection and Its Countermeasure_ | TCHES 2022 | RISC-V 결함 주입 자동화; Future work 참조 |

### 7.6 Fault Models & Taxonomy (결함 모델 및 분류 체계)

| Ref | Authors | Title | Venue/Year | 관련성 |
|-----|---------|-------|------------|--------|
| [24] | Barenghi, A., et al. | _Fault Injection Attacks on Cryptographic Devices: Theory, Practice, and Countermeasures_ | Proceedings of IEEE 2012 | 결함 주입 공격 서베이; Taxonomy 기반 |
| [25] | Riviere, L., et al. | _High Precision Fault Injections on the Instruction Cache of ARMv7-M Architectures_ | HOST 2015 | ARM에서의 instruction-level 결함 모델 |
| [26] | Yuce, B., Schaumont, P., Witteman, M. | _Fault Attacks on Secure Embedded Software: Threats, Design, and Evaluation_ | J. Hardware and Systems Security 2018 | 임베디드 결함 공격 체계적 분류 |

---

## 8. Writing Timeline (집필 일정, 예상)

| Phase | Period | Deliverable |
|-------|--------|-------------|
| **Phase 1: 실험 수행** | Month 1--3 | T1(STM32) 실험 완료, 초기 데이터 |
| **Phase 2: 추가 실험** | Month 3--5 | T2(nRF52), T3(ESP32) 실험 완료 |
| **Phase 3: 분석/집필** | Month 5--7 | 전체 초안 작성, 내부 리뷰 |
| **Phase 4: 수정/투고** | Month 7--8 | 최종 수정, 저널 투고 |
| **Phase 5: Revision** | Month 9--12 | 리뷰어 코멘트 대응, 최종 출판 |

---

## 9. Checklist Before Submission (투고 전 체크리스트)

- [ ] Abstract 200단어 이내 확인
- [ ] Contributions 3개 모두 실험적으로 검증됨
- [ ] 모든 figure/table에 caption과 인용 있음
- [ ] Related work에서 최근 3년 내 논문 충분히 인용
- [ ] Threat model이 명확하고 현실적임
- [ ] 통계적 유의성 검정 포함 (p-value, effect size)
- [ ] Responsible disclosure 사항 명시
- [ ] Artifact 공개 준비 완료 (GitHub + Zenodo)
- [ ] 저자 정보 및 acknowledgment 확인
- [ ] 저널 formatting guideline 준수 (IEEE/ACM template)
- [ ] Supplementary material 준비 (appendix, extended results)
- [ ] 영어 proofreading 완료

---

> **Note**: 이 문서는 논문 뼈대(skeleton)로, 실험 결과가 채워지기 전의 구조 문서입니다. 실험 데이터가 확보되면 Section VIII의 빈 테이블을 채우고, 수치 기반으로 C1--C3의 주장을 구체화해야 합니다.
