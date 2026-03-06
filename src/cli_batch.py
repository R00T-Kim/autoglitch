"""Batch command helpers for AUTOGLITCH CLI queue/soak flows."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml  # type: ignore[import-untyped]

from .cli_support import (
    _aggregate_rerun_results,
    _build_soak_resume_key,
    _create_queue_checkpoint_template,
    _create_soak_checkpoint_template,
    _execute_queue_job,
    _execute_soak_batch,
    _is_serial_soak,
    _load_queue_checkpoint,
    _load_soak_checkpoint,
    _prepare_queue_jobs,
    _queue_has_serial_jobs,
    _queue_job_key,
    _resolve_queue_checkpoint_path,
    _resolve_soak_checkpoint_path,
    _update_queue_checkpoint,
    _update_soak_checkpoint,
)

ExecuteCampaign = Callable[[argparse.Namespace], dict[str, Any]]
WriteJsonReport = Callable[[str, dict[str, Any]], Path]
LoadRunConfig = Callable[[argparse.Namespace], tuple[dict[str, Any], str | None]]
ValidateRuntimeConfig = Callable[..., list[str]]
RunHilPreflightForArgs = Callable[..., dict[str, Any] | None]



def queue_run(
    args: argparse.Namespace,
    *,
    execute_campaign: ExecuteCampaign,
    write_json_report: WriteJsonReport,
) -> None:
    queue_path = Path(args.queue)
    if not queue_path.exists():
        raise SystemExit(f"queue file not found: {queue_path}")
    if args.max_workers <= 0:
        raise SystemExit("--max-workers must be > 0")
    if args.job_interval_s < 0:
        raise SystemExit("--job-interval-s must be >= 0")
    if args.max_workers > 1 and not args.continue_on_error:
        raise SystemExit("queue parallel mode requires --continue-on-error")

    payload = yaml.safe_load(queue_path.read_text(encoding="utf-8")) or {}
    defaults = payload.get("defaults", {})
    jobs = payload.get("jobs", [])

    if not isinstance(jobs, list) or not jobs:
        raise SystemExit("queue yaml must include non-empty `jobs` list")

    prepared_jobs = _prepare_queue_jobs(jobs, respect_order=args.respect_order)
    if not prepared_jobs:
        raise SystemExit("queue has no executable jobs (all jobs disabled?)")

    cli_overrides = {
        "config_mode": getattr(args, "config_mode", None),
        "serial_io": getattr(args, "serial_io", None),
        "rl_backend": getattr(args, "rl_backend", None),
        "ai_mode": getattr(args, "ai_mode", None),
        "policy_file": getattr(args, "policy_file", None),
        "require_preflight": bool(getattr(args, "require_preflight", False)),
        "run_tag": getattr(args, "run_tag", None),
    }

    if (
        args.max_workers > 1
        and _queue_has_serial_jobs(
            prepared_jobs,
            defaults,
            cli_plugin_dirs=args.plugin_dir,
            cli_overrides=cli_overrides,
        )
        and not args.allow_parallel_serial
    ):
        raise SystemExit("parallel serial queue is blocked by default; add --allow-parallel-serial to override")

    checkpoint_file = _resolve_queue_checkpoint_path(args.checkpoint_file, queue_path)
    queue_digest = hashlib.sha256(queue_path.read_bytes()).hexdigest()
    checkpoint_data = _create_queue_checkpoint_template(queue_path, queue_digest)
    completed_keys: set[str] = set()

    if args.resume:
        loaded = _load_queue_checkpoint(checkpoint_file)
        if loaded:
            loaded_digest = str(loaded.get("queue_digest", ""))
            if loaded_digest and loaded_digest != queue_digest:
                raise SystemExit(
                    "checkpoint queue digest mismatch. queue file changed; start fresh or remove checkpoint."
                )
            checkpoint_data = loaded
            completed_keys = set(str(item) for item in loaded.get("completed_job_keys", []))

    order_lookup: dict[str, int] = {}
    pending_items: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for order_idx, item in enumerate(prepared_jobs):
        idx = int(item["index"])
        priority = int(item["priority"])
        job = item["job"]
        job_name = str(job.get("name", f"job_{idx}"))
        job_key = _queue_job_key(idx, job_name)
        order_lookup[job_key] = order_idx

        if job_key in completed_keys:
            results.append(
                {
                    "job_index": idx,
                    "job_name": job_name,
                    "priority": priority,
                    "status": "skipped_resume",
                    "_order": order_idx,
                }
            )
            continue

        pending_items.append(item)

    if args.max_workers == 1:
        for item in pending_items:
            job_key, record = _execute_queue_job(
                item=item,
                defaults=defaults,
                cli_plugin_dirs=args.plugin_dir,
                execute_campaign=execute_campaign,
                cli_overrides=cli_overrides,
            )
            record["_order"] = order_lookup[job_key]
            results.append(record)
            if record["status"] == "completed":
                completed_keys.add(job_key)
            _update_queue_checkpoint(
                checkpoint_data=checkpoint_data,
                checkpoint_file=checkpoint_file,
                completed_keys=completed_keys,
                job_key=job_key,
                job_name=record["job_name"],
                job_index=int(record["job_index"]),
                priority=int(record["priority"]),
                status=str(record["status"]),
                error=record.get("error"),
            )

            if args.job_interval_s > 0:
                time.sleep(args.job_interval_s)

            if record["status"] == "failed" and not args.continue_on_error:
                raise SystemExit(record.get("error", {}).get("message", "queue job failed"))
    else:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            future_map = {}
            for item in pending_items:
                future = executor.submit(
                    _execute_queue_job,
                    item=item,
                    defaults=defaults,
                    cli_plugin_dirs=args.plugin_dir,
                    execute_campaign=execute_campaign,
                    cli_overrides=cli_overrides,
                )
                future_map[future] = item
                if args.job_interval_s > 0:
                    time.sleep(args.job_interval_s)

            for future in as_completed(future_map):
                job_key, record = future.result()
                record["_order"] = order_lookup[job_key]
                results.append(record)
                if record["status"] == "completed":
                    completed_keys.add(job_key)
                _update_queue_checkpoint(
                    checkpoint_data=checkpoint_data,
                    checkpoint_file=checkpoint_file,
                    completed_keys=completed_keys,
                    job_key=job_key,
                    job_name=record["job_name"],
                    job_index=int(record["job_index"]),
                    priority=int(record["priority"]),
                    status=str(record["status"]),
                    error=record.get("error"),
                )

    results = sorted(results, key=lambda item: int(item.get("_order", 10**9)))
    for item in results:
        item.pop("_order", None)

    failed_jobs = [job for job in results if job.get("status") == "failed"]
    skipped_jobs = [job for job in results if job.get("status") == "skipped_resume"]

    summary = {
        "schema_version": 1,
        "queue": str(queue_path),
        "queue_digest": queue_digest,
        "run_tag": getattr(args, "run_tag", None),
        "ai_mode": getattr(args, "ai_mode", None),
        "checkpoint_file": str(checkpoint_file),
        "executed_jobs": len(results),
        "completed_jobs": len([job for job in results if job.get("status") == "completed"]),
        "failed_jobs": len(failed_jobs),
        "skipped_jobs": len(skipped_jobs),
        "jobs": results,
    }
    report_path = write_json_report("queue", summary)
    summary["queue_report"] = str(report_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))



def soak_run(
    args: argparse.Namespace,
    *,
    execute_campaign: ExecuteCampaign,
    load_run_config: LoadRunConfig,
    validate_runtime_config: ValidateRuntimeConfig,
    run_hil_preflight_for_args: RunHilPreflightForArgs,
    write_json_report: WriteJsonReport,
) -> None:
    if args.batch_trials <= 0:
        raise SystemExit("--batch-trials must be > 0")
    if args.duration_minutes <= 0 and args.max_batches is None:
        raise SystemExit("set positive --duration-minutes or provide --max-batches")
    if args.max_workers <= 0:
        raise SystemExit("--max-workers must be > 0")
    if args.batch_interval_s < 0:
        raise SystemExit("--batch-interval-s must be >= 0")
    if args.max_workers > 1 and not args.continue_on_error:
        raise SystemExit("soak parallel mode requires --continue-on-error")
    if args.max_workers > 1 and _is_serial_soak(args) and not args.allow_parallel_serial:
        raise SystemExit("parallel serial soak is blocked by default; add --allow-parallel-serial to override")

    soak_preflight: dict[str, Any] | None = None
    if bool(getattr(args, "require_preflight", False)):
        soak_config, _ = load_run_config(args)
        errors = validate_runtime_config(soak_config, mode=getattr(args, "config_mode", "strict"))
        if errors:
            raise SystemExit("config validation failed:\n- " + "\n- ".join(errors))

        soak_preflight = run_hil_preflight_for_args(args, config=soak_config, force=True)
        if soak_preflight and not bool(soak_preflight.get("valid", False)):
            report_path = soak_preflight.get("report")
            raise SystemExit(f"HIL preflight failed. report={report_path}")

    start_monotonic = time.monotonic()
    end_time = (
        start_monotonic + max(0.0, args.duration_minutes) * 60.0
        if args.duration_minutes > 0
        else float("inf")
    )
    max_batches = args.max_batches or 10**9
    base_seed = args.fixed_seed if args.fixed_seed is not None else 42

    checkpoint_file = _resolve_soak_checkpoint_path(args)
    soak_key = _build_soak_resume_key(args)
    checkpoint_data = _create_soak_checkpoint_template(args, soak_key)

    if args.resume:
        loaded = _load_soak_checkpoint(checkpoint_file)
        if loaded:
            if str(loaded.get("soak_key", "")) != soak_key:
                raise SystemExit(
                    "soak checkpoint mismatch. options changed; start fresh or use a different checkpoint-file."
                )
            checkpoint_data = loaded

    runs: list[dict[str, Any]] = list(checkpoint_data.get("runs", []))
    next_batch = len(runs)
    new_batches = 0

    while next_batch < max_batches:
        if new_batches > 0 and time.monotonic() >= end_time:
            break

        wave_size = min(int(args.max_workers), int(max_batches - next_batch))
        batch_indices = [next_batch + i for i in range(wave_size)]

        if args.max_workers == 1:
            batch_records = [
                _execute_soak_batch(
                    args=args,
                    batch_index=batch_indices[0],
                    base_seed=base_seed,
                    start_monotonic=start_monotonic,
                    execute_campaign=execute_campaign,
                )
            ]
        else:
            with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
                future_map = {}
                for idx, batch_index in enumerate(batch_indices):
                    future = executor.submit(
                        _execute_soak_batch,
                        args=args,
                        batch_index=batch_index,
                        base_seed=base_seed,
                        start_monotonic=start_monotonic,
                        execute_campaign=execute_campaign,
                    )
                    future_map[future] = batch_index
                    if args.batch_interval_s > 0 and idx < len(batch_indices) - 1:
                        time.sleep(args.batch_interval_s)

                batch_records = [future.result() for future in as_completed(future_map)]
                batch_records = sorted(batch_records, key=lambda item: int(item.get("batch", 0)))

        for record in batch_records:
            runs.append(record)
            new_batches += 1
            next_batch += 1
            _update_soak_checkpoint(checkpoint_data, checkpoint_file, runs, soak_key, next_batch + 1)
            if record.get("status") == "failed" and not args.continue_on_error:
                raise SystemExit(record.get("error", {}).get("message", "soak batch failed"))
            if args.batch_interval_s > 0 and args.max_workers == 1:
                time.sleep(args.batch_interval_s)

        if time.monotonic() >= end_time and new_batches >= 1:
            break

    completed_runs = [run for run in runs if run.get("status") == "completed"]
    aggregate = _aggregate_rerun_results(completed_runs, float(args.success_threshold or 0.3))
    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(),
        "mode": "soak",
        "checkpoint_file": str(checkpoint_file),
        "resumed": bool(args.resume),
        "run_tag": getattr(args, "run_tag", None),
        "ai_mode": getattr(args, "ai_mode", None),
        "objective_mode": getattr(args, "objective", None),
        "new_batches": new_batches,
        "batches": len(runs),
        "completed_batches": len(completed_runs),
        "failed_batches": len([run for run in runs if run.get("status") == "failed"]),
        "batch_trials": int(args.batch_trials),
        "duration_minutes": float(args.duration_minutes),
        "runs": runs,
        "aggregate": aggregate,
    }
    if soak_preflight is not None:
        payload["preflight"] = soak_preflight
    report_path = write_json_report("soak", payload)
    payload["soak_report"] = str(report_path)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
