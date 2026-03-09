# ChipWhisperer Adapter Plan

_Updated: 2026-03-09_

> 구현 상태 메모(2026-03-09): `chipwhisperer-hardware` profile/adapter는 현재 registry에
> 통합되어 있고, detect/setup/doctor/run/healthcheck와 strict config path가 동작한다.
> 아직 남은 것은 advanced trigger/capture semantics와 target별 실장비 튜닝이다.

## 1. 목적
이 문서는 AUTOGLITCH를 **ChipWhisperer backend**와 연결하기 위한 설계 초안이다.

왜 먼저 ChipWhisperer를 붙여야 하는가?
- 가장 강한 선행 기준선이다.
- 연구/산업 생태계에서 인지도가 높다.
- AUTOGLITCH의 차별점인 **backend-independent orchestration**을 입증하기 위한 첫 외부 backend로 적합하다.

관련 문서:
- `docs/ROADMAP.md`
- `docs/RESEARCH_POSITIONING.md`
- `docs/PLUGIN_SDK.md`
- ChipWhisperer docs:
  - overview: https://chipwhisperer.readthedocs.io/en/v6.0.0b/Capture/overview.html
  - scope API: https://chipwhisperer.readthedocs.io/en/latest/scope-api.html
  - target API: https://chipwhisperer.readthedocs.io/en/v6.0.0b/target-api.html

---

## 2. 현재 코드베이스와의 연결 지점

현재 AUTOGLITCH 하드웨어 경로는 크게 두 층이다.

### 2.1 Hardware framework registry
- `src/hardware/framework.py`
- `src/hardware/_framework_adapters.py`
- `src/hardware/_framework_models.py`
- `src/hardware/_framework_resolution.py`

이 경로가 실제로
- detect
- setup
- doctor
- resolve
- create
를 책임진다.

### 2.2 Plugin manifest layer
- `src/plugins/manifests/*.yaml`
- `docs/PLUGIN_SDK.md`

현재 observer/classifier/mapper는 runtime plugin wiring이 가능하지만,
**hardware는 아직 framework registry 중심**이다.

### 결론
ChipWhisperer 지원은 최소한 아래 두 곳에 모두 반영돼야 한다.
1. **hardware framework adapter 구현**
2. **plugin manifest / 문서 정합성 반영**

---

## 3. 지원 범위 v1

### v1 목표
- OpenADC 계열 기준 support
  - CW-Lite
  - CW-Pro
  - CW-Husky
- 기본 실험 경로 지원
  - detect
  - setup
  - doctor
  - preflight
  - run
- target serial/UART와의 최소 연결 지원
- report/metadata에 CW-specific 필드 저장

### v1 비목표
- power analysis 캡처 통합
- advanced segmented capture
- TraceWhisperer 계열 통합
- FPGA target(CW305/CW310) 전용 흐름
- Husky 전용 고급 기능 전체 노출

---

## 4. 제안 adapter ID / profile

### adapter ID
```text
chipwhisperer-hardware
```

### 제안 hardware profile
파일 예시:
```text
configs/hardware_profiles/chipwhisperer-hardware.yaml
```

초안:
```yaml
adapter_id: chipwhisperer-hardware
display_name: ChipWhisperer Scope Backend
transport: usb
protocol: chipwhisperer-api
supported_targets:
  - stm32f3
  - stm32f1
  - esp32
capabilities:
  - glitch.execute
  - target.reset
  - target.trigger
  - healthcheck
  - cw.scope
metadata:
  vendor: newae
```

### 제안 plugin manifest
파일 예시:
```text
src/plugins/manifests/chipwhisperer-hardware.yaml
```

역할:
- list-plugins / 문서 정합성 확보
- 장기적으로 hardware plugin runtime 전환 시 대비

---

## 5. 제안 config shape v1

```yaml
hardware:
  adapter: chipwhisperer-hardware
  transport: usb
  target:
    baudrate: 115200
    timeout: 0.25
  chipwhisperer:
    name: Husky        # Lite | Pro | Husky
    sn: null           # optional serial number
    force_program: false
    prog_speed: 10000000
    target_type: simpleserial
    target_serial_mode: auto
    glitch_mode: voltage
    trigger_source: ext_single
    output_mode: enable_only
    io:
      glitch_hp: true
      glitch_lp: false
```

### 비고
- `name`, `sn`는 공식 `cw.scope()` 인자와 맞춘다.
- 공식 문서상 `cw.scope(..., sn=...)`와 `cw.list_devices()`를 사용할 수 있다.
- multi-device 환경에서는 `sn`를 우선 식별자로 사용한다.

---

## 6. detection / setup / resolution 계획

### 6.1 Detect
공식 문서상 `chipwhisperer.list_devices()`가 존재하므로,
1차 detect는 이를 활용하는 방향이 적절하다.

#### v1 detect 전략
1. `cw.list_devices()`로 연결된 NewAE 장비 나열
2. `name`, `sn`, `hw_loc` 수집
3. config의 `name`/`sn`와 일치하는 후보 선택
4. candidate metadata에 device info 저장

#### 출력 예시
- `name`: Husky / Lite / Pro
- `sn`
- `hw_loc`
- optional serial ports (`get_serial_ports()` 가능 시)

### 6.2 Setup
`setup-hardware` 시 아래를 저장한다.
- selected device serial number
- model name
- associated serial ports (가능 시)
- default target serial mapping

### 6.3 Resolution
resolution 우선순위는 기존 구조를 따른다.
1. explicit adapter/config override
2. saved local binding
3. auto-detect
4. fallback

단, CW는 USB 장비이므로 `location`에는 USB hw_loc 또는 serial number 기반 식별자를 저장하는 것이 좋다.

---

## 7. create() 경로 설계

### 제안 클래스
```text
src/hardware/chipwhisperer_hardware.py
```

### 제안 클래스명
```python
class ChipWhispererHardware:
    ...
```

### 책임
- `cw.scope()` 연결
- target serial 연결 확보
- glitch/reset/trigger 실행 래핑
- healthcheck 제공
- cleanup/disconnect 제공

### 내부 상태
- `scope`
- `target` 또는 target serial handle
- resolved model name / serial number
- effective glitch config

---

## 8. AUTOGLITCH 파라미터 ↔ CW 매핑 계획

AUTOGLITCH 공통 파라미터:
- `width`
- `offset`
- `voltage`
- `repeat`
- `ext_offset`

### 매핑 원칙
1. 공통 파라미터 의미를 유지한다.
2. CW가 직접 지원하지 않는 필드는 metadata로 남긴다.
3. backend-specific detail은 hidden mapping으로 처리하되 report에는 기록한다.

### v1 권장 매핑
| AUTOGLITCH | CW 측 의미 | 비고 |
| --- | --- | --- |
| `width` | `scope.glitch` width 계열 | 장비 모델별 표현 차이 주의 |
| `offset` | `scope.glitch` offset 계열 | 장비별 단위 차이 주의 |
| `repeat` | glitch repeat / ext_offset 관련 설정 | 모델별 제약 차이 반영 |
| `ext_offset` | 가능 시 ext_offset 계열 사용 | 미지원 시 degrade 기록 |
| `voltage` | 직접 1:1 대응 안 될 수 있음 | HP/LP crowbar / external setup metadata로 기록 |

### 중요한 주의점
ChipWhisperer의 glitch 표현은 장비/펌웨어/모드에 따라 다를 수 있으므로,
v1에서는 **공통 의미 유지 + mapping metadata 기록**을 우선한다.

---

## 9. healthcheck / doctor / preflight 계획

### 9.1 healthcheck
최소 확인 항목:
- `cw.scope()` 연결 성공
- `scope.fw_version` 조회 가능
- `scope.feature_list()` 또는 동등 정보 조회 가능
- target serial 경로 확보 가능 여부

### 9.2 doctor
진단 결과에 아래를 포함한다.
- no_device
- permission_error
- duplicate_scope_candidates
- target_serial_missing
- firmware_mismatch_warning
- unsupported_feature_warning

### 9.3 preflight
CW-specific preflight는 아래를 점검한다.
- scope/target 연결 안정성
- reset/trigger path sanity
- small probe campaign success rate
- latency / timeout / reset 비율
- mapping sanity (glitch parameter envelope)

---

## 10. report / metadata 확장 계획

### 필수 저장 필드
- cw model name
- cw serial number
- hw_loc (가능 시)
- firmware version
- selected glitch mode
- mapping note
- associated serial ports

### artifact bundle 연결
bundle에는 아래를 넣는다.
- `chipwhisperer_metadata.json`
- optional firmware note
- optional hardware photo

---

## 11. 테스트 계획

### Unit
- detect path가 `cw.list_devices()` mock으로 후보를 올바르게 생성하는지
- config mapping이 올바른 binding/create 인자를 만드는지
- adapter가 metadata를 올바르게 summary에 전달하는지
- unsupported mapping이 degrade note로 기록되는지

### Integration
- mocked ChipWhisperer API로 end-to-end run
- setup → doctor → preflight → run 경로 테스트
- 동일 benchmark schema를 Pi bridge와 CW backend에서 모두 소비하는지

### Manual / Lab
- CW Lite/Husky 중 1종으로 STM32F3 단일 타깃 smoke
- Pi bridge와 동일 benchmark를 최소 1세트 실행
- bundle/evidence pack 생성 확인

---

## 12. 단계별 구현 순서

### Step 1 — 문서/스키마
- profile yaml 초안
- config schema 초안
- adapter class skeleton

### Step 2 — detection/setup
- `cw.list_devices()` 기반 detect
- local binding 저장
- doctor 최소 구현

### Step 3 — execution
- `cw.scope()` 기반 create
- reset/trigger/glitch 래핑
- cleanup 보장

### Step 4 — preflight/report
- CW-specific health/preflight
- metadata/report 연결

### Step 5 — benchmark
- Pi bridge vs CW 비교 benchmark 수행

---

## 13. 위험 요소 / 오픈 이슈

1. **장비별 API/기능 차이**
   - Lite / Pro / Husky / Nano 차이
   - v1은 OpenADC 계열 우선

2. **voltage 파라미터의 공통 의미 유지 문제**
   - CW는 crowbar/IO 중심이고,
     AUTOGLITCH의 `voltage`는 backend-independent 추상 파라미터다.
   - mapping note와 metadata가 필수다.

3. **target serial 경로 통합 문제**
   - target UART를 CW 측 CDC로 볼지,
   - 외부 UART adapter로 볼지 정해야 한다.

4. **권한/USB 환경 이슈**
   - detect/doctor에서 명시적으로 안내해야 한다.

---

## 14. 성공 기준

ChipWhisperer adapter 도입이 성공했다고 말하려면:
1. `detect-hardware`에서 CW 장비가 식별된다.
2. `setup-hardware`로 local binding이 저장된다.
3. `doctor-hardware`와 `hil-preflight`가 CW에서 동작한다.
4. `run`이 CW backend로 실행된다.
5. 결과가 Pi bridge와 **동일 summary/bundle schema**로 저장된다.
6. STM32F3 기준 최소 1세트 benchmark 비교 결과가 나온다.

---

## 15. 한 줄 요약

> ChipWhisperer adapter의 목적은 AUTOGLITCH를 또 하나의 glitching tool로 만드는 것이 아니라,
> **ChipWhisperer를 포함한 이종 backend를 공통 실험 절차로 묶는 상위 orchestration framework**로 만드는 것이다.
