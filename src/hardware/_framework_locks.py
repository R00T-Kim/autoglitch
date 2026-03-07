"""Advisory binding locks for serial hardware usage."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ._framework_models import DEFAULT_LOCK_DIR, HardwareBinding, HardwareResolutionError

_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


def hardware_lock_path(
    binding: HardwareBinding | dict[str, Any] | None,
    *,
    lock_dir: Path = DEFAULT_LOCK_DIR,
) -> Path | None:
    if binding is None:
        return None
    if isinstance(binding, dict):
        adapter_id = str(binding.get("adapter_id", "")).strip()
        transport = str(binding.get("transport", "")).strip().lower()
        location = str(binding.get("location", "")).strip()
    else:
        adapter_id = binding.adapter_id
        transport = binding.transport.lower()
        location = binding.location
    if not adapter_id or not location or transport in {"", "virtual"}:
        return None
    digest = hashlib.sha256(f"{adapter_id}|{transport}|{location}".encode()).hexdigest()[:16]
    return lock_dir / f"{adapter_id}-{digest}.lock"


@contextmanager
def hardware_binding_lock(
    binding: HardwareBinding | dict[str, Any] | None,
    *,
    timeout_s: float = 0.0,
    lock_dir: Path = DEFAULT_LOCK_DIR,
):
    lock_path = hardware_lock_path(binding, lock_dir=lock_dir)
    if lock_path is None:
        yield None
        return

    import fcntl

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = str(lock_path.resolve())
    with _PROCESS_LOCKS_GUARD:
        process_lock = _PROCESS_LOCKS.setdefault(lock_key, threading.Lock())

    if not process_lock.acquire(timeout=max(0.0, timeout_s)):
        raise HardwareResolutionError(f"hardware binding is already in use: {lock_path}")

    deadline = time.monotonic() + max(0.0, timeout_s)
    acquired = False
    try:
        with open(lock_path, "a+", encoding="utf-8") as handle:
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    handle.seek(0)
                    handle.truncate()
                    handle.write(f"pid={os.getpid()}\n")
                    handle.flush()
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise HardwareResolutionError(
                            f"hardware binding is already in use: {lock_path}"
                        ) from exc
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            try:
                yield lock_path
            finally:
                if acquired:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        process_lock.release()
