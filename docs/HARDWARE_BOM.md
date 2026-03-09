# AUTOGLITCH Hardware BOM

_Updated: 2026-03-09_

이 문서는 AUTOGLITCH를 실제로 붙이기 위한 **실사용 하드웨어 BOM**을 정리한 문서다.
현재 저장소의 권장 경로는 **typed serial (`serial-json-hardware`, `autoglitch.v1`)** 이며,
브리지 호스트로는 **Raspberry Pi GPIO bridge**(`src/tools/rpi_glitch_bridge.py`)를 기준으로 잡는다.

관련 문서:
- `docs/REAL_HARDWARE_CHECKLIST.md`
- `docs/RUNBOOK.md`
- `src/tools/rpi_glitch_bridge.py`

---

## 1. 설계 기준

### 현재 저장소와 가장 잘 맞는 경로
1. 호스트 PC에서 `autoglitch` 실행
2. Raspberry Pi가 `rpi_glitch_bridge` 실행
3. Pi가 GPIO로 glitch/reset/trigger 제어
4. 타깃 보드는 UART로 상태를 반환

### BOM 작성 원칙
- **지금 repo에 바로 붙일 수 있는 조합**을 우선 추천한다.
- 특정 제조사 lock-in 대신 **대체 가능한 범주형 부품**도 함께 적는다.
- Pi GPIO는 3.3V이므로 **직결보다 보호/드라이버 단**을 권장한다.
- 연구실형 BOM은 **관측 가능성(scope/logic analyzer/power)** 을 포함한다.

---

# 2. BOM A — Raspberry Pi용(최소 실사용형)

목표:
- 실장비 1대를 AUTOGLITCH에 붙여서 `detect-hardware → setup-hardware → doctor-hardware → hil-preflight → run` 까지 진행
- 비용과 구성 복잡도를 낮추면서도 typed serial 경로를 유지

## 2.1 필수 품목

| 분류 | 품목 | 권장 예시 | 수량 | 우선순위 | 비고 |
| --- | --- | --- | ---: | --- | --- |
| 브리지 호스트 | Raspberry Pi 5 | 8GB 권장 | 1 | 필수 | `rpi_glitch_bridge` 실행 |
| Pi 전원 | USB-C PSU | Raspberry Pi 공식 27W/45W급 | 1 | 필수 | 전원 부족 방지 |
| Pi 냉각 | Active cooler / 팬 | Raspberry Pi Active Cooler 권장 | 1 | 높음 | soak/장시간 실행 안정화 |
| 저장장치 | microSD | 32GB 이상, A1/A2급 | 1 | 필수 | Raspberry Pi OS 설치 |
| 디버그/UART | USB-UART / Debug Probe | Raspberry Pi Debug Probe 권장 | 1 | 필수 | 타깃 UART 확인/SWD 보조 |
| 타깃 보드 | MCU dev board | STM32 NUCLEO-F303RE 권장 | 1~2 | 필수 | repo 기본 타깃(`stm32f3`)과 잘 맞음 |
| 배선 | 점퍼선, GND 공통, 핀헤더 | 2.54mm 점퍼선 세트 | 1식 | 필수 | reset/trigger/UART 연결 |
| 보호/구동단 | 3.3V-safe 트랜지스터/MOSFET 드라이버 보드 | 범용 N-MOSFET/BJT 소신호 단계 | 1식 | 필수 | Pi GPIO 직접 구동 최소화 |
| 호스트 PC | 개발용 PC | Linux/macOS/Windows | 1 | 필수 | `autoglitch` 실행 및 결과 수집 |

## 2.2 권장 추가 품목

| 분류 | 품목 | 권장 예시 | 수량 | 이유 |
| --- | --- | --- | ---: | --- |
| 관측 | 간단한 로직애널라이저 | 8채널급 USB LA | 1 | trigger/reset/UART 타이밍 확인 |
| 예비 타깃 | 동일 MCU 보드 | NUCLEO-F303RE 추가 | 1 | 실험 중 보드 손상 대비 |
| USB 안정화 | USB 절연기 | 범용 절연기 | 1 | 노이즈/그라운드 문제 완화 |
| 전원 보호 | TVS/퓨즈/저항 | 소형 보호 부품 | 1식 | 잘못된 배선 피해 축소 |

## 2.3 권장 배선 역할

| 신호 | 연결 주체 | 설명 |
| --- | --- | --- |
| GND | Pi ↔ target ↔ 외부 전원 | 반드시 공통 GND |
| UART TX/RX | Pi/Debug Probe ↔ target | 상태 수집 |
| Reset | Pi GPIO ↔ 드라이버 ↔ target reset | `reset` 명령용 |
| Trigger out | Pi GPIO ↔ target trigger 입력 | 수동 trigger 발생 |
| Trigger in(선택) | target ↔ Pi GPIO | external trigger 대기 |
| Glitch | Pi GPIO ↔ 드라이버 ↔ glitch injection path | crowbar/펄스 구동 |

## 2.4 이 구성의 장단점

### 장점
- 현재 repo와 가장 직접적으로 맞는다.
- 소프트웨어 bring-up이 빠르다.
- typed serial 경로를 바로 검증할 수 있다.

### 단점
- glitch 품질/정밀도는 전용 FI 장비보다 떨어질 수 있다.
- 드라이버 단 설계 품질에 따라 재현성이 크게 좌우된다.
- 측정 장비가 없으면 실패 원인 분석이 어렵다.

## 2.5 구매 우선순위

1. Raspberry Pi 5 + PSU + cooler
2. STM32 NUCLEO-F303RE
3. USB-UART/Debug Probe
4. 점퍼선/헤더/보호·구동단
5. 간단한 로직애널라이저
6. 예비 타깃 보드

---

# 3. BOM B — 연구실용(관측/재현성 강화형)

목표:
- AUTOGLITCH를 실제 랩 운영 수준으로 사용
- 파형/타이밍/전원 상태를 함께 관측
- RC validation, soak, recovery drill까지 수행 가능한 구성 확보

## 3.1 필수 품목

| 분류 | 품목 | 권장 예시 | 수량 | 우선순위 | 비고 |
| --- | --- | --- | ---: | --- | --- |
| 제어 워크스테이션 | Linux PC/노트북 | 개발환경 가능한 시스템 | 1 | 필수 | `autoglitch`, 분석, 아티팩트 보관 |
| 브리지 호스트 | Raspberry Pi 5 | 8GB 권장 | 1 | 필수 | 현재 repo와 직접 호환 |
| Pi 전원 | USB-C PSU | 공식 27W/45W급 | 1 | 필수 | 안정 구동 |
| Pi 냉각 | Active cooler | 공식/동급 | 1 | 높음 | soak 안정화 |
| 타깃 보드 | MCU dev board | STM32 NUCLEO-F303RE | 2+ | 필수 | 실험용 + 예비 |
| 오실로스코프 | 4채널 DSO | Siglent SDS1104X-E 급 | 1 | 필수 | glitch/reset/trigger/UART 파형 확인 |
| 벤치 전원공급기 | 프로그래머블 DC PSU | Siglent SPD3303X-E 급 | 1 | 필수 | 안정 전원, 채널 분리 |
| 로직애널라이저 | 8ch 이상 | Saleae Logic 8 급 | 1 | 필수 | 디지털 타이밍 분석 |
| 디버그/UART | USB-UART / Debug Probe | Raspberry Pi Debug Probe | 1 | 필수 | UART/SWD bring-up |
| 보호/구동단 | 레벨시프터/드라이버/보호 보드 | 3.3V-safe 설계 | 1식 | 필수 | Pi/target 보호 |
| 배선/프로빙 | 점퍼/BNC/probe/grabber | 실험실 계측용 세트 | 1식 | 필수 | 반복 연결/계측 |
| ESD 장비 | ESD mat + wrist strap | 범용 | 1식 | 높음 | 보드 보호 |

## 3.2 권장 추가 품목

| 분류 | 품목 | 권장 예시 | 수량 | 이유 |
| --- | --- | --- | ---: | --- |
| 고급 로직애널라이저 | 상위 샘플링 모델 | Saleae Logic Pro 8 급 | 1 | 빠른 디지털 캡처 |
| 광학 관찰 | USB 현미경/매크로 카메라 | 범용 | 1 | 납땜/배선 확인 |
| 전원/USB 절연 | 절연기 | 범용 | 1~2 | 접지 루프 완화 |
| 브리지 예비기 | Raspberry Pi 추가 | Pi 4/5 가능 | 1 | bridge 장애 시 즉시 교체 |
| 타깃 예비군 | 동일 보드 추가 | NUCLEO-F303RE | 1~3 | 손상/변동성 대응 |

## 3.3 운영상 강한 이유
- AUTOGLITCH 결과와 **파형 관측**을 연결할 수 있다.
- timeout/reset/crash 원인을 **전원 문제인지 timing 문제인지** 구분하기 쉬워진다.
- `hil-preflight`, `validate-hil-rc`, `soak`, `queue-run` 검증 신뢰도가 올라간다.

## 3.4 구매 우선순위

1. 제어 PC + Raspberry Pi 5 세트
2. 타깃 보드 2장 이상
3. 벤치 전원공급기
4. 오실로스코프
5. 로직애널라이저
6. 디버그 프로브
7. ESD/절연/예비 자산

---

# 4. 공통 소모품 BOM

| 품목 | 권장 수량 | 메모 |
| --- | ---: | --- |
| 수-수 점퍼선 | 1팩 이상 | 실험 중 가장 빨리 소모/분실 |
| 수-암/암-암 점퍼선 | 1팩 이상 | Pi/보드/브레드보드 혼합 연결용 |
| 2.54mm 핀헤더 | 여러 줄 | 보드 개조/브레이크아웃 |
| 브레드보드/퍼프보드 | 1~2 | 드라이버 단계 프로토타이핑 |
| 소신호 MOSFET/BJT | 여러 개 | reset/glitch 구동단 구성 |
| 저항/커패시터 세트 | 1식 | 풀업/풀다운/RC 조정 |
| 미니 grabber clip | 1세트 | 테스트 포인트 연결 |
| 예비 USB 케이블 | 2~3 | UART/전원 문제 대비 |

---

# 5. 권장 타깃 조합

## 가장 먼저 추천
- **타깃:** STM32 NUCLEO-F303RE
- **브리지:** Raspberry Pi 5 + `src.tools.rpi_glitch_bridge`
- **프로토콜:** `serial-json-hardware` (`autoglitch.v1`)

이유:
- repo 기본 예시가 `stm32f3` 중심이다.
- typed serial 경로와 운영 문서가 가장 잘 맞는다.
- bring-up 난이도가 상대적으로 낮다.

---

# 6. 비권장/주의 사항

- **Pi GPIO를 보호 없이 직접 고전류 crowbar 경로에 물리지 말 것**
- target와 Pi 사이에 **공통 GND** 없이는 UART/trigger/glitch 모두 불안정해질 수 있음
- 처음부터 고가 장비를 많이 사기보다,
  **Pi형 BOM으로 bring-up → 연구실형 BOM으로 확장** 순서가 낫다
- 이 repo는 현재 기준으로 **전용 FI 장비(예: ChipWhisperer) 네이티브 런타임 통합이 중심은 아님**
  - 붙일 수는 있지만 adapter/bridge/plugin 추가 작업이 필요하다

---

# 7. 빠른 추천안

## 최소 실사용 구매안
- Raspberry Pi 5
- USB-C PSU
- Active Cooler
- Raspberry Pi Debug Probe
- STM32 NUCLEO-F303RE
- 점퍼선/헤더
- 3.3V-safe 드라이버 단계 부품

## 연구실 표준 구매안
- 최소 구매안 전체
- 벤치 전원공급기 1대
- 4채널 오실로스코프 1대
- 로직애널라이저 1대
- 예비 타깃 보드 1~3장
- ESD/절연/프로빙 세트

---

# 8. 다음 액션

구매 후 권장 순서:
1. `python -m src.cli validate-config --target stm32f3`
2. `python -m src.cli detect-hardware --target stm32f3 --serial-port /dev/ttyUSB0`
3. `python -m src.cli setup-hardware --target stm32f3 --serial-port /dev/ttyUSB0 --force`
4. `python -m src.cli doctor-hardware --target stm32f3`
5. `python -m src.cli hil-preflight --target stm32f3`
6. `python -m src.cli run --target stm32f3 --require-preflight --trials 100`
7. 필요 시 `python -m src.cli validate-hil-rc ...`
