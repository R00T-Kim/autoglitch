# AUTOGLITCH Artifact Bundle Schema v1

_Updated: 2026-03-09_

> 구현 상태 메모(2026-03-09): v1 bundle generator는 현재 campaign summary, run manifest,
> trial log, metadata, hardware resolution, operator notes, optional preflight/RC report를
> 자동으로 수집하고 completeness를 계산한다. 남은 것은 실장비 photo/scope/logic 자산의
> 운영 절차를 고정하는 일이다.

## 1. 목적
이 문서는 AUTOGLITCH의 연구 차별점 중 **reproducible operations**를 실현하기 위한
**artifact bundle 규약**을 정의한다.

핵심 아이디어는 단순하다.

> 실험 결과 JSON 하나만 남기는 것이 아니라,
> **실험을 다시 이해하고, 재현하고, 감사(audit)할 수 있는 최소 증거 단위**를 한 폴더로 묶는다.

관련 문서:
- `docs/ROADMAP.md`
- `docs/BENCHMARK_SCHEMA.md`
- `docs/REAL_HARDWARE_CHECKLIST.md`

---

## 2. Bundle이 필요한 이유

fault injection 실험은 아래 요인에 매우 민감하다.
- 보드 상태
- 배선
- 전원
- bridge/backend 상태
- 날짜/온도/운영자
- seed / optimizer 상태

따라서 “결과가 나왔다”만 저장하면 연구 증거로 약하다.
AUTOGLITCH는 결과를 반드시 **context-rich evidence pack**으로 묶어야 한다.

---

## 3. Bundle의 역할

artifact bundle은 아래 세 역할을 동시에 수행한다.

1. **재현성 기록물**
2. **논문/보고용 evidence pack**
3. **실험실 운영 감사 기록(audit trail)**

---

## 4. Directory convention v1

기본 저장 경로 권장안:

```text
experiments/results/bundles/<YYYYMMDD>/<benchmark_id>/<target>/<backend>/<run_id>/
```

예시:

```text
experiments/results/bundles/20260309/bm_pi_stm32f3_detfault_v1/stm32f3_nucleo/pi-bridge/run_20260309_142233/
```

### Evidence pack 경로(실장비용)

```text
experiments/results/real_hardware/<YYYYMMDD>_<target>_<backend>_<run_id>/
```

둘은 동일한 내용을 다르게 노출하는 alias일 수 있다.
- `bundles/...` : benchmark 중심
- `real_hardware/...` : 운영/실장비 중심

---

## 5. 필수 파일

| 파일 | 필수 여부 | 설명 |
| --- | --- | --- |
| `bundle_manifest.json` | 필수 | bundle index / 버전 / 파일 링크 |
| `campaign_summary.json` | 필수 | run summary |
| `run_manifest.json` | 필수 | config hash / git SHA / runtime fingerprint |
| `trial_log.jsonl` | 필수 | trial 단위 로그 |
| `preflight.json` | 필수 | preflight 결과 |
| `hardware_resolution.json` | 필수 | detect/setup/selected binding 정보 |
| `operator_notes.md` | 필수 | 운영자 메모 |
| `metadata.json` | 필수 | target/board/wiring/prep/operator/lab metadata |

---

## 6. 조건부 필수 파일

| 파일 | 조건 | 설명 |
| --- | --- | --- |
| `rc_validation.json` | `validate-hil-rc` 실행 시 | RC 검증 리포트 |
| `decision_trace.jsonl` | agentic/planner 사용 시 | decision trace |
| `optimizer_telemetry.json` | optimizer telemetry 사용 시 | fit/acquisition/runtime telemetry |
| `training_report.json` | RL 학습 경로 사용 시 | train/eval report |
| `queue_summary.json` | queue-run 시 | queue summary |
| `soak_summary.json` | soak 실행 시 | soak summary |

---

## 7. 권장 추가 파일

| 파일 | 설명 |
| --- | --- |
| `wiring.md` | 배선 설명, 핀맵, 연결 메모 |
| `board_prep.md` | 캡 제거, 점퍼 변경, 커팅 등 준비 작업 |
| `power_setup.md` | PSU 전압/전류 설정 |
| `photos/` | 배선/보드/실험 셋업 사진 |
| `scope/` | 오실로스코프 캡처 또는 CSV 경로 |
| `logic/` | 로직애널라이저 캡처/세션 파일 |
| `firmware/` | target firmware hash / build info |
| `env/` | host OS / Python / dependency snapshot |

---

## 8. `bundle_manifest.json` 최소 스키마

```json
{
  "schema_version": 1,
  "bundle_id": "bundle_20260309_stm32f3_pi_run01",
  "created_at": "2026-03-09T14:22:33+09:00",
  "benchmark_id": "bm_pi_stm32f3_detfault_v1",
  "target": "stm32f3_nucleo",
  "backend": "pi-bridge",
  "run_id": "run_20260309_142233",
  "files": {
    "campaign_summary": "campaign_summary.json",
    "run_manifest": "run_manifest.json",
    "trial_log": "trial_log.jsonl",
    "preflight": "preflight.json",
    "hardware_resolution": "hardware_resolution.json",
    "metadata": "metadata.json",
    "operator_notes": "operator_notes.md"
  },
  "assets": {
    "photos": ["photos/setup_front.jpg"],
    "scope": ["scope/boot_glitch_01.png"],
    "logic": []
  },
  "completeness": {
    "required_ok": true,
    "optional_count": 4
  }
}
```

---

## 9. `metadata.json` 최소 스키마

```json
{
  "schema_version": 1,
  "target": {
    "family": "stm32f3",
    "board_model": "NUCLEO-F303RE",
    "board_id": "board_a",
    "board_revision": "rev_x",
    "firmware_id": "fw_sha256:..."
  },
  "backend": {
    "name": "pi-bridge",
    "adapter": "serial-json-hardware",
    "device_id": "rpi5_bridge_01"
  },
  "lab": {
    "site": "lab_a",
    "operator": "rootk1m",
    "date": "2026-03-09"
  },
  "setup": {
    "wiring_profile": "wf_stm32f3_pi_v1",
    "board_prep_profile": "prep_c12_removed",
    "power_profile": "psu_3v3_ch1_v1"
  }
}
```

---

## 10. Completeness rule

### Required complete
아래가 모두 존재하면 bundle은 `required_ok=true` 이다.
- summary
- manifest
- trial log
- preflight
- hardware resolution
- metadata
- operator notes

### Research-complete
논문/보고 수준의 bundle은 추가로 아래를 권장한다.
- wiring 문서
- board prep 문서
- 최소 1장 이상의 setup photo
- scope 또는 logic analyzer 자산 1개 이상
- target firmware 식별자

### RC-complete
실장비 RC validation용 bundle은 추가로 아래를 요구한다.
- `rc_validation.json`
- queue/soak 관련 결과(해당 시)
- recovery drill confirmation

---

## 11. Operator notes 최소 내용

`operator_notes.md`에는 아래 항목을 남긴다.
- 실험 목적
- anomaly 관찰 사항
- 수동 개입 내용
- 예상과 다른 점
- 다음 실행에서 바꿀 점

짧아도 되지만, 빈 파일이면 안 된다.

---

## 12. Bundle 생성 규칙

### 자동 생성 대상
가능한 한 아래는 자동 생성한다.
- bundle directory
- bundle manifest
- summary/manifest/log/preflight 링크
- config hash / git SHA / runtime fingerprint 연결

### 수동 보완 대상
아래는 초기에 수동 입력을 허용한다.
- wiring note
- board prep note
- photo attachment
- scope/logic analyzer asset
- operator notes

초기에는 하이브리드 방식으로 시작하고,
후속 단계에서 입력 UI/CLI를 개선한다.

---

## 13. Bundle과 benchmark의 관계

- **benchmark summary**는 여러 bundle을 집계한 결과다.
- **artifact bundle**은 한 번의 실험 run을 완전하게 보관하는 단위다.

즉:
- benchmark = 비교/통계 단위
- bundle = 증거/감사 단위

둘을 분리해야 연구와 운영 모두 깔끔해진다.

---

## 14. 구현 우선순위

### 바로 구현
1. bundle directory generator
2. bundle manifest writer
3. 기존 summary/manifest/log/preflight 경로 연결
4. metadata stub writer
5. operator note stub writer

### 다음 구현
1. RC validation 자동 포함
2. asset auto-discovery/linking
3. bundle zip export
4. completeness checker
5. replay-from-bundle helper

---

## 15. 성공 기준

artifact bundle 도입이 성공했다고 보려면:
1. run 하나가 bundle 하나로 저장된다.
2. operator가 바뀌어도 맥락을 이해할 수 있다.
3. benchmark summary에서 원본 bundle로 역추적할 수 있다.
4. 논문/리뷰에서 “증거를 보여달라” 했을 때 바로 제시 가능하다.

---

## 16. 한 줄 요약

> AUTOGLITCH artifact bundle은 결과 파일 모음이 아니라,
> **fault injection 실험을 재현·감사·비교 가능하게 만드는 최소 증거 단위**다.
