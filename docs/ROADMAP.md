# AUTOGLITCH Roadmap (8 Weeks)

## Goal
Deliver a reproducible dual-target (STM32F3 + ESP32) closed-loop glitching workflow that can reach exploitable primitives and report reproducibility metrics.

## Primary KPI
- **Primitive reproducibility rate**: ratio of repeated primitive hits under fixed settings.

## Current Status (2026-03-05)
- ✅ Strict config / safety / recovery baseline
- ✅ Queue/soak/replay/benchmark 운영 경로
- ✅ Async serial persistent + reconnect
- ✅ Serial HIL preflight (`hil-preflight`, `--require-preflight`)
- ✅ BO vectorized heuristic + telemetry
- ✅ Campaign summary schema v4 (latency/throughput/Pareto/optimizer runtime)
- ✅ CI lint/typecheck gate hardening (fail-fast)
- 🔜 Next: SB3 실학습 경로, TuRBO/qNEHVI 실험, HIL 게이트 강화

## Milestones

### Weeks 1-2 — Foundation
- ✅ Fix packaging/runtime path consistency and CLI entrypoint.
- ✅ Implement Bayesian optimizer baseline (`random -> surrogate -> acquisition`).
- ✅ Add end-to-end smoke run path with mock hardware.
- ✅ Add unit tests for optimizer/classifier/orchestrator basics.

### Weeks 3-4 — Classification & Mapping
- ✅ Expand rule-based classifier for instruction skip/data corruption/auth bypass patterns.
- ✅ Improve primitive mapping confidence from observation features.
- ✅ Normalize target configs for STM32F3 and ESP32.
- ✅ Standardize report schema (`campaign_id`, rates, distributions, run metadata).

### Weeks 5-6 — Reproducibility Pipeline
- ✅ Define fixed-seed rerun campaign template.
- ✅ Compute and report `time_to_first_primitive` and `primitive_repro_rate`.
- ✅ Add integration tests for state transitions and report generation.
- ✅ Add failure categorization tags in trial metadata.
- ✅ Add latency/throughput/Pareto runtime metrics (`schema_version: 4`).

### Weeks 7-8 — RL/LLM Minimal Integration
- ✅ Add lightweight RL optimizer path (optional module switch).
- ✅ Add heuristic LLM advisor fallback for strategy/hypothesis text output.
- ✅ Produce BO vs RL-lite comparison reports.
- ✅ Freeze docs for reproducible runbook.

## Next Wave (Research/Performance)
1. SB3 실학습 파이프라인(callback/eval/checkpoint 연동)
2. TuRBO backend 및 multi-objective (qNEHVI 계열) 실험 브랜치
3. HIL gate: serial jitter/timeout stress, 재현성/안정성 기준선 확정

## Deliverables
- `autoglitch run` and `autoglitch report` CLI flow.
- Campaign JSON report + trial JSONL logs.
- Test suite covering baseline logic and integration smoke path.
- Architecture + research + roadmap docs synchronized.
