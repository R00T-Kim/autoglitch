# AUTOGLITCH Software Evolution Research (2026-03-05)

외부 레퍼런스(공식 문서/공식 레포) 기반으로, 현재 코드베이스에서 **실제 효과가 큰 소프트웨어 개선 항목**을 우선순위로 정리했다.

## 적용 현황 스냅샷 (2026-03-06)
- ✅ Pydantic strict config 계층 적용
- ✅ Serial async bridge + persistent/reconnect 적용
- ✅ Serial HIL preflight + 실행 전 강제 게이트(`--require-preflight`)
- ✅ report schema v4(throughput/latency/Pareto/optimizer telemetry) 적용
- ✅ report schema v5(재현성 fingerprint/objective/training) 적용
- ✅ RL train/eval CLI + SB3 checkpoint/eval facade 적용
- ✅ BO backend 확장(`turbo`, `qnehvi`) + objective mode 적용
- ✅ Agentic planner/policy skeleton + decision trace(report v6) + knowledge CLI 적용
- ✅ CodeQL/Semgrep 워크플로우 + CI gate hardening 적용
- ⏳ botorch-native TuRBO/qNEHVI 정교화는 다음 단계

## 1) 지금 바로 적용 가능한 Quick Wins

### A. CI 보안/신뢰성 강화
- GitHub 공식 보안 가이드 기준으로:
  - 액션을 태그(`@v5`) 대신 **full SHA pinning**으로 고정
  - `.github/workflows/*` 변경에 `CODEOWNERS` 리뷰 강제
  - `GITHUB_TOKEN` 최소 권한 유지
- 이미 Dependabot 설정은 추가됨(`.github/dependabot.yml`).

### B. 테스트 실행시간 단축
- `pytest-xdist`(`pytest -n auto`) 도입으로 unit test wall-time 단축 가능.
- 현재 테스트 수(40+) 기준으로 CI 체감 개선이 큼.

### C. 설정 검증 강도 상향
- 현재 validator + safety 체크는 있음.
- 여기에 Pydantic strict 모드(`ConfigDict(strict=True)` 등) 추가하면
  YAML 타입 강제(문자열→정수 자동 coercion 방지)가 쉬워짐.

## 2) 중기 개선 (실험 성능/재현성)

### D. BO 고도화 (Botorch 권장 경로)
- 고차원/국소 최적화 문제에 TuRBO 계열 추가.
- 다중 목표(예: success_rate + 장비안전/속도)에서는 qNEHVI 계열 적용 검토.
- 현재 heuristic/GP 2트랙 구조와 자연스럽게 병행 가능.

### E. RL 학습 안정화
- Stable-Baselines3의 `EvalCallback`, `CheckpointCallback`, `CallbackList`를 정식 파이프라인에 연결.
- 벡터화 환경(`DummyVecEnv`/`SubprocVecEnv`)으로 학습 샘플 throughput 개선.

### F. 실험 추적 고도화
- MLflow 3 Tracking API 기준으로:
  - nested run(캠페인/배치/trial)
  - dataset input logging
  - model/artifact lineage를 명시화

## 3) 장비 연동 소프트웨어 개선

### G. Serial I/O 비동기화
- 현재는 동기 `read_until` 기반.
- pyserial-asyncio(공식 pyserial 팀, docs 마지막 업데이트 2021) 기반 비동기 브리지 옵션을 추가하면
  queue/soak 병렬 제어 시 호스트 블로킹을 줄일 수 있음.
- 단, 유지보수 활성도는 낮아 보여(2021 release) 파일럿 적용 후 채택 판단 권장.

## 4) 보안 스캔 체계

### H. 코드 스캔 자동화
- GitHub CodeQL default setup 활성화(공개 레포에서 빠르게 시작 가능).
- Semgrep CI job 추가(정책/규칙 커스터마이징 용이).

---

## 제안 실행 순서 (추천)
1. **CI 보안 하드닝 + xdist 도입**
2. **Pydantic strict config layer 추가**
3. **RL callbacks + 벡터 환경**
4. **TuRBO/qNEHVI 실험 브랜치**
5. **MLflow nested/data lineage 정식화**
6. **Serial async bridge 파일럿**

---

## Source Links (Primary)
- GitHub setup-python (cache/pip): https://github.com/actions/setup-python
- GitHub Python build/test docs: https://docs.github.com/actions/guides/building-and-testing-python
- GitHub Actions secure use (SHA pinning, CODEOWNERS, Dependabot, 최소권한): https://docs.github.com/en/actions/reference/security/secure-use
- BoTorch TuRBO: https://botorch.org/docs/tutorials/turbo_1/
- BoTorch constrained MOBO (qNEHVI): https://botorch.org/docs/next/tutorials/constrained_multi_objective_bo/
- Hydra Structured Configs: https://hydra.cc/docs/1.2/tutorials/structured_config/intro/
- Hydra Compose API: https://hydra.cc/docs/1.1/advanced/compose_api/
- Pydantic Strict Mode: https://docs.pydantic.dev/latest/concepts/strict_mode/
- MLflow Tracking API: https://mlflow.org/docs/latest/ml/tracking/tracking-api/
- SB3 Callbacks: https://stable-baselines3.readthedocs.io/en/v2.6.0/guide/callbacks.html
- SB3 Vectorized Envs: https://stable-baselines3.readthedocs.io/en/master/guide/vec_envs.html
- pytest-xdist: https://pytest-xdist.readthedocs.io/en/stable/distribution.html
- Hypothesis docs: https://hypothesis.readthedocs.io/
- pySerial API: https://pythonhosted.org/pyserial/pyserial_api.html
- pyserial-asyncio docs: https://pyserial-asyncio.readthedocs.io/en/latest/
- pyserial-asyncio repo (latest release metadata): https://github.com/pyserial/pyserial-asyncio
- GitHub CodeQL default setup: https://docs.github.com/en/code-security/how-tos/scan-code-for-vulnerabilities/configure-code-scanning/configuring-default-setup-for-code-scanning
- Semgrep CI docs: https://semgrep.dev/docs/deployment/add-semgrep-to-ci
