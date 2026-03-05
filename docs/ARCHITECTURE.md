# AUTOGLITCH 시스템 아키텍처

> **"LLM이 못하는 하드웨어 해킹을 AI가 하게 만드는"** closed-loop 자동 글리칭 시스템

## 최근 소프트웨어 업데이트 (2026-03-06)

- **Strict Config 계층**: `pydantic` 기반 strict schema 검증 (`--config-mode strict|legacy`)
- **Serial I/O 모드 분리**: `sync`(기본) + `async` 옵션 (`--serial-io async`) + persistent/reconnect 상태머신
- **HIL 사전검증 게이트**: `hil-preflight` + `--require-preflight`로 serial 안정성 확인 후 캠페인 실행
- **RL 학습/평가 경로**: `train-rl` / `eval-rl` + SB3 facade checkpoint/load/eval
- **BO backend 확장**: `auto|heuristic|botorch|turbo|qnehvi` + objective mode(`single|multi`)
- **Agentic 제어 계층**: Planner Proposal → Policy Gate → Patch Apply 루프 (`run-agentic`)
- **지식 계층 베이스라인**: `kb-ingest`/`kb-query` 로컬 지식 저장소
- **추적 고도화**: campaign summary `schema_version: 6`, decision trace 포함
- **보안 파이프라인**: CI + CodeQL + Semgrep 워크플로우 분리

---

## 목차

1. [전체 개요](#1-전체-개요)
2. [설계 철학](#2-설계-철학)
3. [시스템 데이터 흐름](#3-시스템-데이터-흐름)
4. [모듈 상세 설계](#4-모듈-상세-설계)
   - [A. Experiment Orchestrator](#a-experiment-orchestrator)
   - [B. Glitch Parameter Optimizer](#b-glitch-parameter-optimizer)
   - [C. Hardware Interface Layer](#c-hardware-interface-layer)
   - [D. Observation Collector](#d-observation-collector)
   - [E. Fault Classifier](#e-fault-classifier)
   - [F. Primitive Mapper](#f-primitive-mapper)
   - [G. LLM Advisor](#g-llm-advisor)
   - [H. Logging & Visualization](#h-logging--visualization)
5. [핵심 데이터 타입](#5-핵심-데이터-타입)
6. [설정 관리](#6-설정-관리)
7. [디렉터리 구조](#7-디렉터리-구조)
8. [의존성 스택](#8-의존성-스택)

---

## 1. 전체 개요

AUTOGLITCH는 voltage/clock fault injection 공격을 자동화하는 closed-loop 시스템이다.
핵심 아이디어는 다음과 같다:

- **AI가 장비를 직접 제어**하여 글리치를 실행한다.
- **측정 결과를 자동으로 해석**하여 fault를 분류한다.
- **Bayesian Optimization / RL**로 최적 파라미터를 탐색한다.
- **성공 여부를 자동 검증**하여 exploitable primitive로 매핑한다.
- **LLM은 숫자 최적화를 하지 않는다.** 전략 자문, 가설 생성, 결과 해석만 담당한다.

즉, 사람이 오실로스코프를 보면서 파라미터를 손으로 조정하던 과정을
AI가 자율적으로 수행하는 것이 목표다.

```
사람의 직관    →  AI의 자동화
────────────────────────────────
"이 정도 전압?"  →  Bayesian Optimizer가 suggest
"리셋됐나?"      →  Observer가 감지
"뭐가 깨졌지?"   →  Classifier가 분류
"이거 쓸 수 있나?" →  Mapper가 primitive 판정
"다음엔 뭘 해볼까?" →  LLM Advisor가 전략 제안
```

---

## 2. 설계 철학

| 원칙 | 설명 |
|------|------|
| **Closed-Loop** | 파라미터 제안 → 실행 → 관측 → 분류 → 피드백의 완전 자동 루프 |
| **하드웨어 추상화** | 글리처/타깃/오실로스코프를 ABC로 추상화하여 장비 교체 가능 |
| **AI = 제어자, LLM = 자문역** | 숫자 최적화는 BO/RL, LLM은 고차원 전략만 담당 |
| **Fault-to-Primitive** | 단순 fault 발견이 아닌 exploit 가능 여부까지 자동 판정 |
| **재현성** | 모든 trial을 MLflow로 추적, 시드 고정, 설정 YAML 분리 |
| **안전** | voltage/current 리밋, watchdog timer로 장비 보호 |

---

## 3. 시스템 데이터 흐름

### 3.1 메인 루프 다이어그램

```
                    ┌─────────────────┐
                    │   LLM Advisor   │
                    │  (전략/가설/해석) │
                    └────────┬────────┘
                             │ 전략 자문
                             ▼
┌──────────────────────────────────────────────────────────┐
│                  Experiment Orchestrator                  │
│                   (전체 루프 관리자)                       │
│                                                          │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐            │
│  │  INIT   │───▶│CONFIGURE │───▶│  GLITCH   │            │
│  └─────────┘    └──────────┘    └─────┬─────┘            │
│                                       │                  │
│  ┌─────────┐    ┌──────────┐    ┌─────▼─────┐            │
│  │FEEDBACK │◀───│   MAP    │◀───│  OBSERVE  │            │
│  └────┬────┘    └──────────┘    └─────┬─────┘            │
│       │                               │                  │
│       │         ┌──────────┐    ┌─────▼─────┐            │
│       └────────▶│ 반복/종료 │◀───│ CLASSIFY  │            │
│                 └──────────┘    └───────────┘            │
└──────────────────────────────────────────────────────────┘
                             │
                             ▼ 매 trial 기록
                    ┌─────────────────┐
                    │ Logging & Viz   │
                    │ (MLflow/Dash)   │
                    └─────────────────┘
```

### 3.2 모듈 간 데이터 흐름

```
[Optimizer]  ──suggest()──▶  GlitchParameters
                                    │
[Hardware]   ◀──execute()───────────┘
     │
     └──────────────────▶  RawResult
                                │
[Observer]   ◀──collect()───────┘
     │
     └──────────────────▶  Observation
                                │
[Classifier] ◀──classify()─────┘
     │
     └──────────────────▶  FaultClass
                                │
[Mapper]     ◀──map()───────────┘
     │
     └──────────────────▶  ExploitPrimitive
                                │
[Optimizer]  ◀──observe()───────┘  (reward 피드백)
[Logger]     ◀──log_trial()─────┘  (전체 기록)
```

---

## 4. 모듈 상세 설계

---

### A. Experiment Orchestrator

**경로:** `src/orchestrator/`

**역할:** 전체 closed-loop 실험 루프를 관리하는 중앙 컨트롤러.
Optimizer에서 파라미터를 받아 Hardware로 글리치를 실행하고,
Observer로 결과를 수집한 뒤 Classifier와 Mapper를 거쳐
다시 Optimizer에 피드백하는 일련의 과정을 조율한다.

**핵심 클래스:**

```python
class ExperimentOrchestrator:
    """전체 실험 루프를 관리하는 중앙 오케스트레이터."""

    def __init__(
        self,
        optimizer: BaseOptimizer,
        glitcher: BaseGlitcher,
        target: BaseTarget,
        observer: ObservationCollector,
        classifier: FaultClassifier,
        mapper: PrimitiveMapper,
        logger: ExperimentLogger,
        advisor: LLMAdvisor | None = None,
    ) -> None: ...

    def run_experiment(self, config: ExperimentConfig) -> ExperimentResult:
        """단일 실험(1 trial)을 실행한다."""
        ...

    def run_campaign(self, config: CampaignConfig, n_trials: int) -> CampaignResult:
        """n_trials만큼 실험을 반복 실행하는 캠페인을 수행한다."""
        ...
```

**상태 머신:**

```
INIT ──▶ CONFIGURE ──▶ GLITCH ──▶ OBSERVE ──▶ CLASSIFY ──▶ MAP ──▶ FEEDBACK
  ▲                                                                    │
  └────────────────────── 반복 (n_trials 미달) ◀───────────────────────┘
                          종료 (n_trials 달성 또는 목표 도달)
```

| 상태 | 수행 작업 |
|------|----------|
| `INIT` | 장비 연결, 초기 설정 로드 |
| `CONFIGURE` | Optimizer에서 다음 파라미터 요청 (`suggest()`) |
| `GLITCH` | Hardware에 파라미터 전달 후 글리치 실행 |
| `OBSERVE` | Observer로 시리얼 출력, 응답 시간, 리셋 여부 수집 |
| `CLASSIFY` | Classifier로 fault class 분류 |
| `MAP` | Mapper로 exploitable primitive 매핑 |
| `FEEDBACK` | Optimizer에 (params, reward) 피드백 전달 |

**인터페이스:**

```python
run_experiment(config: ExperimentConfig) -> ExperimentResult
run_campaign(config: CampaignConfig, n_trials: int) -> CampaignResult
```

---

### B. Glitch Parameter Optimizer

**경로:** `src/optimizer/`

**역할:** 글리치 파라미터 공간을 탐색하고 최적의 파라미터 조합을 찾는다.
Bayesian Optimization, Reinforcement Learning, Random Search, Grid Search 네 가지 전략을 지원한다.

**핵심 클래스:**

```python
class BaseOptimizer(ABC):
    """모든 옵티마이저의 추상 기반 클래스."""

    @abstractmethod
    def suggest(self) -> GlitchParameters:
        """다음 시도할 글리치 파라미터를 제안한다."""
        ...

    @abstractmethod
    def observe(self, params: GlitchParameters, result: TrialResult) -> None:
        """실행 결과를 옵티마이저에 피드백한다."""
        ...

    @abstractmethod
    def get_best(self) -> tuple[GlitchParameters, float]:
        """지금까지의 최적 파라미터와 점수를 반환한다."""
        ...


class BayesianOptimizer(BaseOptimizer):
    """BoTorch/Ax 기반 Bayesian Optimization."""
    # GP surrogate model + acquisition function (EI, UCB, PI)
    ...

class RLOptimizer(BaseOptimizer):
    """Stable-Baselines3 기반 강화학습 옵티마이저."""
    # 커스텀 GlitchEnv(gym.Env) 환경 사용
    ...

class RandomSearchOptimizer(BaseOptimizer):
    """랜덤 탐색 (베이스라인)."""
    ...

class GridSearchOptimizer(BaseOptimizer):
    """격자 탐색 (완전 탐색)."""
    ...
```

**파라미터 공간:**

```python
@dataclass
class GlitchParameters:
    width: float       # 글리치 펄스 폭 (ns/클럭 사이클)
    offset: float      # 트리거 후 글리치 시작까지 오프셋
    voltage: float     # 글리치 전압 레벨
    repeat: int        # 글리치 반복 횟수
    ext_offset: float  # 외부 트리거 오프셋 (선택)
```

**Bayesian Optimization 세부 사항:**

| 구성 요소 | 구현 |
|-----------|------|
| Surrogate Model | Gaussian Process (BoTorch `SingleTaskGP`) |
| Acquisition Function | Expected Improvement (EI), Upper Confidence Bound (UCB), Probability of Improvement (PI) |
| 초기 탐색 | `n_initial` (기본 50) 포인트 랜덤 샘플링 |
| 프레임워크 | BoTorch + Ax Platform |

**RL 세부 사항:**

| 구성 요소 | 구현 |
|-----------|------|
| 환경 | 커스텀 `GlitchEnv(gym.Env)` |
| 상태 공간 | 이전 파라미터 + 이전 결과 특징 |
| 행동 공간 | 연속 파라미터 공간 (Box) |
| 보상 함수 | fault severity 기반 (NORMAL=0, RESET=-0.1, 의미있는 fault=+1.0) |
| 알고리즘 | PPO (Stable-Baselines3) |

---

### C. Hardware Interface Layer

**경로:** `src/hardware/`

**역할:** 물리적 하드웨어 장비(글리처, 타깃, 오실로스코프)를
추상화하여 나머지 시스템이 장비 종류에 의존하지 않도록 한다.

**핵심 클래스:**

```python
# ── 글리처 추상화 ──

class BaseGlitcher(ABC):
    """글리치 장비의 추상 인터페이스."""

    @abstractmethod
    def configure(self, params: GlitchParameters) -> None:
        """글리치 파라미터를 장비에 설정한다."""
        ...

    @abstractmethod
    def arm(self) -> None:
        """글리치 트리거 대기 상태로 전환한다."""
        ...

    @abstractmethod
    def execute(self) -> RawResult:
        """글리치를 실행하고 원시 결과를 반환한다."""
        ...

    @abstractmethod
    def disarm(self) -> None:
        """글리치 해제 및 안전 상태로 복귀한다."""
        ...


class ChipWhispererGlitcher(BaseGlitcher):
    """ChipWhisperer 보드 기반 글리처 구현."""
    ...


# ── 타깃 추상화 ──

class BaseTarget(ABC):
    """글리치 대상 디바이스의 추상 인터페이스."""

    @abstractmethod
    def reset(self) -> None:
        """타깃을 리셋한다."""
        ...

    @abstractmethod
    def send_trigger(self) -> None:
        """글리치 트리거 신호를 보낸다."""
        ...

    @abstractmethod
    def read_response(self, timeout: float = 1.0) -> bytes:
        """타깃의 응답을 읽는다."""
        ...


class SerialTarget(BaseTarget):
    """UART 시리얼 인터페이스 타깃."""
    ...

class JTAGTarget(BaseTarget):
    """JTAG 디버그 인터페이스 타깃."""
    ...


# ── 오실로스코프 추상화 ──

class BaseScope(ABC):
    """오실로스코프 추상 인터페이스."""

    @abstractmethod
    def capture_waveform(self) -> np.ndarray:
        """파형을 캡처하여 numpy 배열로 반환한다."""
        ...
```

**안전 장치:**

| 보호 메커니즘 | 설명 |
|-------------|------|
| Voltage Limit | 글리치 전압이 설정된 안전 범위를 초과하면 자동 차단 |
| Current Limit | 타깃 전류가 임계값을 초과하면 즉시 중단 |
| Watchdog Timer | 타깃이 일정 시간 응답하지 않으면 자동 리셋 |
| Graceful Shutdown | 예외 발생 시 장비를 안전 상태로 복귀 (`disarm()`) |

**지원 타깃 (설정 파일):**

| 타깃 | 설정 파일 | 패밀리 |
|------|----------|--------|
| STM32F303 | `configs/targets/stm32f3.yaml` | Cortex-M4 |
| nRF52 | `configs/targets/nrf52.yaml` | Cortex-M4 |
| ESP32 | `configs/targets/esp32.yaml` | Xtensa LX6 |

---

### D. Observation Collector

**경로:** `src/observer/`

**역할:** 글리치 실행 후 타깃으로부터 원시 데이터를 수집하고,
분석에 필요한 형태로 전처리한다.

**핵심 클래스:**

```python
class ObservationCollector:
    """실험 결과를 수집하고 전처리하는 메인 컬렉터."""

    def collect(self, raw_result: RawResult) -> Observation:
        """원시 결과로부터 구조화된 관측 데이터를 생성한다."""
        ...


class SerialObserver:
    """시리얼 출력 기반 관측기."""
    ...

class WaveformObserver:
    """오실로스코프 파형 기반 관측기."""
    ...
```

**수집 데이터:**

| 데이터 | 타입 | 설명 |
|--------|------|------|
| `serial_output` | `bytes` | 타깃의 시리얼 출력 원본 |
| `response_time` | `float` | 글리치 실행 후 응답까지 걸린 시간 (초) |
| `reset_detected` | `bool` | 타깃 리셋 발생 여부 |
| `waveform` | `np.ndarray \| None` | 오실로스코프 캡처 파형 (선택) |
| `features` | `dict[str, float]` | 추출된 특징 벡터 |

**전처리 파이프라인:**

```
RawResult
  │
  ├──▶ 노이즈 필터링 (scipy.signal)
  ├──▶ 정규화 (min-max / z-score)
  └──▶ 특징 추출
        ├── 응답 시간 편차
        ├── 출력 바이트 패턴
        ├── 파형 에너지 (선택)
        └── 주파수 성분 (선택)
```

**인터페이스:**

```python
collect(raw_result: RawResult) -> Observation
```

**Observation 구조:**

```python
@dataclass
class Observation:
    serial_output: bytes          # 시리얼 출력 원본
    response_time: float          # 응답 시간
    reset_detected: bool          # 리셋 감지 여부
    waveform: np.ndarray | None   # 파형 데이터 (선택)
    features: dict[str, float]    # 추출된 특징
```

---

### E. Fault Classifier

**경로:** `src/classifier/`

**역할:** 관측 결과를 분석하여 어떤 종류의 fault가 발생했는지 분류한다.
규칙 기반 분류기와 ML 기반 분류기를 하이브리드로 결합한다.

**Fault Taxonomy (고장 분류 체계):**

| FaultClass | 코드 | 설명 | 대표 증상 |
|------------|------|------|----------|
| `NORMAL` | 0 | 정상 동작 | 기대한 출력 일치 |
| `RESET` | 1 | 타깃 리셋 | 부트 메시지 재출력 |
| `CRASH` | 2 | 비정상 종료 | 응답 없음 / 타임아웃 |
| `INSTRUCTION_SKIP` | 3 | 명령어 건너뜀 | 특정 연산 결과 누락 |
| `DATA_CORRUPTION` | 4 | 데이터 변조 | 출력값 비정상 |
| `AUTH_BYPASS` | 5 | 인증 우회 | 인증 없이 접근 성공 |
| `UNKNOWN` | 6 | 미분류 | 위 카테고리에 해당 없음 |

**핵심 클래스:**

```python
class FaultClassifier:
    """하이브리드 fault 분류기 (규칙 + ML)."""

    def classify(self, observation: Observation) -> FaultClass:
        """단일 관측을 분류한다."""
        ...

    def classify_batch(self, observations: list[Observation]) -> list[FaultClass]:
        """다수 관측을 일괄 분류한다."""
        ...

    def get_confidence(self) -> float:
        """마지막 분류의 신뢰도를 반환한다."""
        ...


class RuleBasedClassifier:
    """결정론적 규칙 기반 분류기."""
    # 리셋 감지 → RESET
    # 타임아웃 → CRASH
    # 기대값 불일치 → DATA_CORRUPTION 또는 INSTRUCTION_SKIP
    ...

class MLClassifier:
    """scikit-learn 기반 ML 분류기."""
    # Random Forest / XGBoost / MLP
    # 특징 벡터 → FaultClass 매핑
    ...
```

**하이브리드 분류 전략:**

```
Observation
  │
  ├──▶ [RuleBasedClassifier] ── 확실한 패턴(리셋, 타임아웃) → 즉시 결정
  │
  └──▶ [MLClassifier] ── 불확실한 경우 ML 모델로 분류
         │
         └──▶ confidence < threshold → UNKNOWN
```

1. 먼저 규칙 기반으로 명확한 패턴을 감지한다 (리셋 메시지, 타임아웃 등).
2. 규칙으로 판정되지 않는 경우 ML 분류기가 특징 벡터를 기반으로 판정한다.
3. ML 분류기의 신뢰도가 임계값 이하이면 `UNKNOWN`으로 분류한다.

**인터페이스:**

```python
classify(observation: Observation) -> FaultClass
classify_batch(observations: list[Observation]) -> list[FaultClass]
get_confidence() -> float
```

---

### F. Primitive Mapper

**경로:** `src/mapper/`

**역할:** 분류된 fault를 실제 exploit에 활용 가능한 primitive로 매핑한다.
단순히 "고장이 났다"를 넘어 "이 고장을 어떻게 악용할 수 있는가"를 판정한다.

**Primitive Types (익스플로잇 프리미티브 유형):**

| ExploitPrimitive | 설명 | 연관 FaultClass |
|-----------------|------|----------------|
| `CONTROL_FLOW_HIJACK` | 제어 흐름 탈취 (PC 변조) | `INSTRUCTION_SKIP` |
| `AUTH_CHECK_BYPASS` | 인증/검증 체크 우회 | `AUTH_BYPASS`, `INSTRUCTION_SKIP` |
| `MEMORY_READ_PRIMITIVE` | 임의 메모리 읽기 | `DATA_CORRUPTION` |
| `MEMORY_WRITE_PRIMITIVE` | 임의 메모리 쓰기 | `DATA_CORRUPTION` |
| `PRIVILEGE_ESCALATION` | 권한 상승 | `AUTH_BYPASS` |
| `CODE_EXECUTION` | 임의 코드 실행 | `CONTROL_FLOW_HIJACK` |
| `NONE` | exploitable 아님 | `NORMAL`, `RESET`, `CRASH` |

**핵심 클래스:**

```python
class PrimitiveMapper:
    """fault class를 exploitable primitive로 매핑한다."""

    def map(self, fault_class: FaultClass, observation: Observation) -> ExploitPrimitive:
        """fault class와 관측 데이터를 기반으로 primitive를 판정한다."""
        ...

    def get_exploitability_score(self) -> float:
        """마지막 매핑의 exploitability 점수를 반환한다 (0.0~1.0)."""
        ...
```

**매핑 로직:**

```
FaultClass + Observation
  │
  ├── NORMAL / RESET / CRASH → NONE (exploitability = 0.0)
  │
  ├── INSTRUCTION_SKIP
  │     ├── 인증 관련 코드 건너뜀? → AUTH_CHECK_BYPASS (0.9)
  │     ├── 분기문 건너뜀?       → CONTROL_FLOW_HIJACK (0.8)
  │     └── 기타               → NONE (0.1)
  │
  ├── DATA_CORRUPTION
  │     ├── 주소 관련 데이터 변조? → MEMORY_READ/WRITE_PRIMITIVE (0.7)
  │     └── 일반 데이터 변조?    → NONE (0.2)
  │
  └── AUTH_BYPASS
        ├── 완전 우회 확인?      → AUTH_CHECK_BYPASS (1.0)
        └── 부분 우회?          → PRIVILEGE_ESCALATION (0.6)
```

**Exploitability Score:**

- `0.0`: exploit 불가능 (정상 동작, 단순 리셋)
- `0.1 ~ 0.3`: 낮은 가능성 (재현 불안정, 조건 까다로움)
- `0.4 ~ 0.6`: 중간 가능성 (추가 분석 필요)
- `0.7 ~ 0.9`: 높은 가능성 (명확한 primitive)
- `1.0`: 확실한 exploit primitive (완전 재현 가능)

---

### G. LLM Advisor

**경로:** `src/llm_advisor/`

**역할:** 실험 설계 자문, 가설 생성, 결과 해석을 담당하는 AI 자문 모듈.
**LLM은 숫자 최적화를 하지 않는다.** 전략적 판단과 고차원 해석만 수행한다.

**LLM vs. Optimizer 역할 분리:**

```
┌─────────────────────────────────────────────────┐
│ LLM Advisor (전략적 사고)                        │
│  "STM32는 clock glitch에 취약할 가능성이 높다.    │
│   offset 범위를 flash read 타이밍에 맞춰보자."    │
├─────────────────────────────────────────────────┤
│ Optimizer (수치 최적화)                           │
│  "offset=12.3, width=4.7, voltage=-0.8이        │
│   현재까지 가장 높은 EI를 보인다."                  │
└─────────────────────────────────────────────────┘
```

**핵심 클래스:**

```python
class LLMAdvisor:
    """LLM 기반 실험 전략 자문 시스템."""

    def suggest_search_strategy(
        self, history: list[TrialResult]
    ) -> SearchStrategy:
        """실험 이력을 분석하여 다음 탐색 전략을 제안한다.
        예: "현재 GP surrogate의 uncertainty가 높은 영역을 우선 탐색하라."
        """
        ...

    def generate_hypothesis(
        self, observations: list[Observation]
    ) -> Hypothesis:
        """관측 데이터로부터 새로운 가설을 생성한다.
        예: "offset 12~15 구간에서 instruction skip이 집중 발생하는 것은
             해당 구간이 flash read와 겹치기 때문일 수 있다."
        """
        ...

    def interpret_results(
        self, campaign_result: CampaignResult
    ) -> Interpretation:
        """캠페인 전체 결과를 해석하여 인사이트를 도출한다."""
        ...

    def suggest_priors(
        self, target_info: dict
    ) -> dict[str, Distribution]:
        """타깃 정보를 기반으로 BO의 prior 분포를 제안한다.
        예: ARM Cortex-M4 타깃의 경우 clock cycle 기반 offset 분포 제안.
        """
        ...
```

**LLM 백엔드:**

| 옵션 | 설명 |
|------|------|
| Claude API | Anthropic Claude (기본) |
| 로컬 LLM | Ollama/vLLM 등 로컬 배포 모델 |

---

### H. Logging & Visualization

**경로:** `src/logging_viz/`

**역할:** 모든 실험 데이터를 기록하고, 실시간 모니터링 및 논문용 그래프를 생성한다.

**핵심 클래스:**

```python
class ExperimentLogger:
    """MLflow 기반 실험 로깅."""

    def log_trial(
        self,
        trial_id: int,
        params: GlitchParameters,
        result: TrialResult,
        fault_class: FaultClass,
        primitive: ExploitPrimitive,
    ) -> None:
        """단일 trial의 모든 정보를 기록한다."""
        ...


class DashboardServer:
    """Plotly Dash 기반 실시간 대시보드."""
    # 실시간 파라미터 공간 탐색 현황
    # fault class 분포 변화
    # convergence plot
    # exploitability 히트맵
    ...


class PaperPlotter:
    """matplotlib 기반 논문용 그래프 생성기."""

    def plot_convergence(self) -> Figure:
        """수렴 곡선(best score vs. trial)을 그린다."""
        ...

    def plot_fault_distribution(self) -> Figure:
        """fault class 분포를 시각화한다."""
        ...

    def export_paper_figures(self, output_dir: str) -> None:
        """논문 삽입용 고해상도 그래프를 일괄 출력한다."""
        ...
```

**MLflow 통합:**

| 추적 대상 | 예시 |
|----------|------|
| 파라미터 | `width=4.7`, `offset=12.3`, `voltage=-0.8` |
| 메트릭 | `fault_class=3`, `exploitability=0.85`, `response_time=0.042` |
| 아티팩트 | 파형 데이터, 분류 모델, 설정 YAML |

**대시보드 패널:**

```
┌───────────────────────────────────────────────┐
│  AUTOGLITCH Live Dashboard                    │
├──────────────────┬────────────────────────────┤
│  Convergence     │  Fault Distribution        │
│  [line chart]    │  [pie chart]               │
├──────────────────┼────────────────────────────┤
│  Parameter Space │  Exploitability Heatmap    │
│  [3D scatter]    │  [width x offset heatmap]  │
├──────────────────┴────────────────────────────┤
│  Trial Log (최근 20건)                         │
│  #1042  w=4.7 o=12.3 v=-0.8  INST_SKIP  0.85 │
│  #1041  w=3.2 o=11.8 v=-0.6  RESET      0.00 │
└───────────────────────────────────────────────┘
```

**논문용 그래프:**

| 그래프 | 파일명 | 설명 |
|--------|--------|------|
| Convergence Plot | `convergence.pdf` | 최적 점수 수렴 곡선 |
| Fault Distribution | `fault_dist.pdf` | fault class별 비율 |
| Parameter Heatmap | `param_heatmap.pdf` | width x offset 탐색 결과 |
| Exploitability CDF | `exploit_cdf.pdf` | exploitability 누적 분포 |
| BO Acquisition | `bo_acquisition.pdf` | acquisition function 시각화 |

---

## 5. 핵심 데이터 타입

모든 데이터 타입은 `dataclass` 또는 `enum`으로 정의되며,
모듈 간 데이터 교환의 계약(contract) 역할을 한다.

```python
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Optional
import numpy as np
from datetime import datetime


# ── 글리치 파라미터 ──

@dataclass(frozen=True)
class GlitchParameters:
    """글리치 실행에 필요한 파라미터 집합."""
    width: float          # 글리치 펄스 폭 (ns 또는 클럭 사이클)
    offset: float         # 트리거 후 글리치까지의 시간 오프셋
    voltage: float        # 글리치 전압 레벨
    repeat: int = 1       # 글리치 반복 횟수
    ext_offset: float = 0.0  # 외부 트리거 오프셋


# ── 원시 결과 ──

@dataclass
class RawResult:
    """하드웨어 실행 후 수집된 가공 전 원시 데이터."""
    serial_output: bytes   # 타깃 시리얼 출력
    response_time: float   # 응답 시간 (초)
    reset_detected: bool   # 리셋 발생 여부
    error_code: int = 0    # 하드웨어 에러 코드 (0 = 정상)


# ── 관측 데이터 ──

@dataclass
class Observation:
    """전처리된 관측 데이터."""
    serial_output: bytes
    response_time: float
    reset_detected: bool
    waveform: Optional[np.ndarray] = None     # 오실로스코프 파형
    features: dict[str, float] = field(default_factory=dict)


# ── Fault 분류 ──

class FaultClass(IntEnum):
    """fault injection 결과 분류."""
    NORMAL = 0             # 정상 동작
    RESET = 1              # 타깃 리셋
    CRASH = 2              # 비정상 종료
    INSTRUCTION_SKIP = 3   # 명령어 건너뜀
    DATA_CORRUPTION = 4    # 데이터 변조
    AUTH_BYPASS = 5        # 인증 우회
    UNKNOWN = 6            # 미분류


# ── Exploit Primitive ──

class ExploitPrimitiveType(IntEnum):
    """exploit 가능한 primitive 유형."""
    NONE = 0
    CONTROL_FLOW_HIJACK = auto()
    AUTH_CHECK_BYPASS = auto()
    MEMORY_READ_PRIMITIVE = auto()
    MEMORY_WRITE_PRIMITIVE = auto()
    PRIVILEGE_ESCALATION = auto()
    CODE_EXECUTION = auto()


@dataclass
class ExploitPrimitive:
    """exploit primitive 판정 결과."""
    primitive_type: ExploitPrimitiveType
    exploitability_score: float  # 0.0 ~ 1.0
    description: str = ""


# ── Trial / Campaign 결과 ──

@dataclass
class TrialResult:
    """단일 trial의 전체 결과."""
    trial_id: int
    params: GlitchParameters
    observation: Observation
    fault_class: FaultClass
    primitive: ExploitPrimitive
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CampaignResult:
    """캠페인(다수 trial) 전체 결과."""
    trials: list[TrialResult]
    total_trials: int
    fault_distribution: dict[FaultClass, int]
    best_trial: TrialResult | None
    best_exploitability: float
    duration_seconds: float
```

**데이터 타입 간 관계:**

```
GlitchParameters ──▶ Hardware ──▶ RawResult ──▶ Observation
                                                     │
                                               FaultClass
                                                     │
                                             ExploitPrimitive
                                                     │
                                               TrialResult
                                                     │
                                             CampaignResult
```

---

## 6. 설정 관리

Hydra + YAML 기반 설정 관리 체계를 사용한다.
설정 파일은 `configs/` 디렉터리에 계층적으로 구성된다.

### 6.1 설정 파일 구조

```
configs/
├── default.yaml          # 기본 설정 (전체 기본값)
└── targets/
    ├── stm32f3.yaml      # STM32F303 타깃 설정
    ├── nrf52.yaml        # nRF52 타깃 설정
    └── esp32.yaml        # ESP32 타깃 설정
```

### 6.2 주요 설정 항목

| 섹션 | 키 | 설명 | 기본값 |
|------|-----|------|-------|
| `experiment` | `name` | 실험 이름 | `"default"` |
| `experiment` | `seed` | 랜덤 시드 | `42` |
| `experiment` | `max_trials` | 최대 시도 횟수 | `10000` |
| `optimizer` | `type` | 옵티마이저 종류 | `"bayesian"` |
| `optimizer.bo` | `n_initial` | BO 초기 랜덤 샘플 수 | `50` |
| `optimizer.bo` | `acquisition` | Acquisition function | `"ei"` |
| `optimizer.rl` | `algorithm` | RL 알고리즘 | `"ppo"` |
| `hardware.glitcher` | `type` | 글리처 종류 | `"chipwhisperer"` |
| `hardware.target` | `type` | 타깃 종류 | `"stm32f3"` |
| `classifier` | `model` | ML 분류 모델 | `"random_forest"` |
| `logging` | `save_waveforms` | 파형 저장 여부 | `false` |

### 6.3 Hydra 사용 예시

```bash
# 기본 설정으로 실행
autoglitch

# nRF52 타깃으로 변경
autoglitch target=nrf52

# RL 옵티마이저 사용 + 파형 저장
autoglitch optimizer.type=rl logging.save_waveforms=true

# 실험 이름 및 시드 변경
autoglitch experiment.name=my_exp experiment.seed=123
```

---

## 7. 디렉터리 구조

```
03_Hardware/
├── configs/                    # Hydra 설정 파일
│   ├── default.yaml            #   기본 설정
│   └── targets/                #   타깃별 설정
│       ├── stm32f3.yaml
│       ├── nrf52.yaml
│       └── esp32.yaml
│
├── src/                        # 소스 코드 (8개 모듈)
│   ├── __init__.py
│   ├── orchestrator/           #   A. 실험 오케스트레이터
│   │   └── __init__.py
│   ├── optimizer/              #   B. 파라미터 옵티마이저
│   │   └── __init__.py
│   ├── hardware/               #   C. 하드웨어 인터페이스
│   │   └── __init__.py
│   ├── observer/               #   D. 관측 수집기
│   │   └── __init__.py
│   ├── classifier/             #   E. Fault 분류기
│   │   └── __init__.py
│   ├── mapper/                 #   F. Primitive 매퍼
│   │   └── __init__.py
│   ├── llm_advisor/            #   G. LLM 자문 모듈
│   │   └── __init__.py
│   ├── logging_viz/            #   H. 로깅 & 시각화
│   │   └── __init__.py
│   └── utils/                  #   공통 유틸리티
│       └── __init__.py
│
├── tests/                      # 테스트
│   ├── __init__.py
│   ├── unit/                   #   단위 테스트
│   │   └── __init__.py
│   └── integration/            #   통합 테스트
│       └── __init__.py
│
├── data/                       # 데이터
│   ├── raw/                    #   원시 데이터
│   ├── processed/              #   전처리 데이터
│   └── datasets/               #   학습용 데이터셋
│
├── experiments/                # 실험 결과
│   ├── results/                #   실험 결과 파일
│   └── logs/                   #   실험 로그
│
├── paper/                      # 논문 관련
│   ├── figures/                #   논문용 그래프
│   └── tables/                 #   논문용 표
│
├── notebooks/                  # Jupyter 노트북 (분석/실험)
├── docs/                       # 문서
│   └── ARCHITECTURE.md         #   본 문서
│
└── pyproject.toml              # 프로젝트 메타/빌드 설정
```

---

## 8. 의존성 스택

### 8.1 핵심 의존성

| 카테고리 | 패키지 | 버전 | 용도 |
|---------|--------|------|------|
| **수치 계산** | numpy | >= 1.24 | 배열 연산, 파형 처리 |
| | scipy | >= 1.11 | 신호 처리, 통계 |
| **베이지안 최적화** | torch | >= 2.1 | BoTorch 백엔드 |
| | botorch | >= 0.10 | GP surrogate + acquisition |
| | ax-platform | >= 0.3 | 실험 관리 프레임워크 |
| **강화학습** | stable-baselines3 | >= 2.2 | PPO/SAC 등 RL 알고리즘 |
| **하드웨어** | pyserial | >= 3.5 | UART 시리얼 통신 |
| | pyvisa | >= 1.14 | 계측기(오실로스코프) 제어 |
| **분류** | scikit-learn | >= 1.3 | Random Forest, MLP 등 |
| **시각화** | matplotlib | >= 3.8 | 논문용 정적 그래프 |
| | plotly | >= 5.18 | 대시보드 인터랙티브 시각화 |
| **실험 추적** | mlflow | >= 2.9 | 파라미터/메트릭/아티팩트 관리 |
| **설정 관리** | pyyaml | >= 6.0 | YAML 파싱 |
| | hydra-core | >= 1.3 | 계층적 설정 관리 |
| **CLI/UX** | rich | >= 13.7 | 터미널 출력 포매팅 |
| | tqdm | >= 4.66 | 진행률 표시 |

### 8.2 개발 의존성

| 패키지 | 용도 |
|--------|------|
| ruff | 린터 + 포매터 |
| mypy | 정적 타입 검사 |
| pytest | 테스트 프레임워크 |
| pytest-cov | 테스트 커버리지 |
| pre-commit | 커밋 전 자동 검사 |
| jupyter + ipykernel | 분석 노트북 |

### 8.3 모듈 간 의존성 그래프

```
orchestrator ──▶ optimizer
             ──▶ hardware
             ──▶ observer
             ──▶ classifier
             ──▶ mapper
             ──▶ llm_advisor (선택)
             ──▶ logging_viz

optimizer    ──▶ (독립, torch/botorch/sb3 사용)
hardware     ──▶ (독립, pyserial/pyvisa 사용)
observer     ──▶ (독립, scipy/numpy 사용)
classifier   ──▶ observer (Observation 타입 참조)
mapper       ──▶ classifier (FaultClass 타입 참조)
             ──▶ observer (Observation 타입 참조)
llm_advisor  ──▶ (독립, LLM API 사용)
logging_viz  ──▶ (독립, mlflow/plotly/matplotlib 사용)
```

**핵심 원칙:** `orchestrator`만이 모든 모듈에 의존한다.
나머지 모듈은 서로에 대한 의존을 최소화하여 독립적으로 테스트 가능하다.

---

> **문서 버전:** v0.1.0
> **최종 수정:** 2026-03-05
> **프로젝트:** AUTOGLITCH - CYAI Lab
