# AUTOGLITCH Roadmap (8 Weeks)

## Goal
Deliver a reproducible dual-target (STM32F3 + ESP32) closed-loop glitching workflow that can reach exploitable primitives and report reproducibility metrics.

## Primary KPI
- **Primitive reproducibility rate**: ratio of repeated primitive hits under fixed settings.

## Milestones

### Weeks 1-2 — Foundation
- Fix packaging/runtime path consistency and CLI entrypoint.
- Implement Bayesian optimizer baseline (`random -> surrogate -> acquisition`).
- Add end-to-end smoke run path with mock hardware.
- Add unit tests for optimizer/classifier/orchestrator basics.

### Weeks 3-4 — Classification & Mapping
- Expand rule-based classifier for instruction skip/data corruption/auth bypass patterns.
- Improve primitive mapping confidence from observation features.
- Normalize target configs for STM32F3 and ESP32.
- Standardize report schema (`campaign_id`, rates, distributions, run metadata).

### Weeks 5-6 — Reproducibility Pipeline
- Define fixed-seed rerun campaign template.
- Compute and report `time_to_first_primitive` and `primitive_repro_rate`.
- Add integration tests for state transitions and report generation.
- Add failure categorization tags in trial metadata.

### Weeks 7-8 — RL/LLM Minimal Integration
- Add lightweight RL optimizer path (optional module switch).
- Add heuristic LLM advisor fallback for strategy/hypothesis text output.
- Produce BO vs RL-lite comparison reports.
- Freeze docs for reproducible runbook.

## Deliverables
- `autoglitch run` and `autoglitch report` CLI flow.
- Campaign JSON report + trial JSONL logs.
- Test suite covering baseline logic and integration smoke path.
- Architecture + research + roadmap docs synchronized.
