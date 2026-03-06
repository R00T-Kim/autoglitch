"""Software-only serial glitch bridge emulator.

This helper exposes a pseudo-terminal (PTY) that accepts both the legacy line protocol used by
``SerialCommandHardware`` and the newer JSONL typed protocol used by
``TypedSerialCommandHardware``. It enables serial-mode end-to-end testing without physical
hardware.
"""
from __future__ import annotations

import argparse
import json
import os
import pty
import select
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from ..hardware import MockHardware
from ..types import GlitchParameters


def parse_glitch_params(command_line: str) -> GlitchParameters:
    """Parse legacy protocol line: ``GLITCH width=... offset=... voltage=... repeat=... ext_offset=...``."""
    line = command_line.strip()
    if not line.upper().startswith("GLITCH "):
        raise ValueError(f"not a GLITCH command: {command_line!r}")

    payload = line.split(" ", 1)[1]
    parts = [chunk for chunk in payload.split(" ") if chunk.strip()]

    parsed: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key.strip().lower()] = value.strip()

    try:
        return GlitchParameters(
            width=float(parsed["width"]),
            offset=float(parsed["offset"]),
            voltage=float(parsed.get("voltage", 0.0)),
            repeat=int(parsed.get("repeat", 1)),
            ext_offset=float(parsed.get("ext_offset", 0.0)),
        )
    except KeyError as exc:
        raise ValueError(f"missing required field in GLITCH command: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"invalid numeric field in GLITCH command: {exc}") from exc


def _parse_typed_params(payload: dict[str, object]) -> GlitchParameters:
    params = payload.get("payload", {})
    if not isinstance(params, dict):
        raise ValueError("typed execute payload must contain a mapping `payload`")
    return GlitchParameters(
        width=float(params.get("width", 0.0)),
        offset=float(params.get("offset", 0.0)),
        voltage=float(params.get("voltage", 0.0)),
        repeat=int(params.get("repeat", 1)),
        ext_offset=float(params.get("ext_offset", 0.0)),
    )


@dataclass
class MockGlitchBridge:
    """PTY-backed mock bridge server."""

    seed: int = 42
    response_delay_s: float = 0.0
    adapter_id: str = "serial-json-hardware"

    def __post_init__(self) -> None:
        self._master_fd: int | None = None
        self._slave_fd: int | None = None
        self.port: str | None = None
        self._buffer = b""
        self._hardware = MockHardware(seed=self.seed)

    def open_pty(self) -> str:
        if self._master_fd is not None and self._slave_fd is not None and self.port is not None:
            return self.port
        self._master_fd, self._slave_fd = pty.openpty()
        self.port = os.ttyname(self._slave_fd)
        return self.port

    def close(self) -> None:
        for fd in (self._master_fd, self._slave_fd):
            if fd is None:
                continue
            with suppress(OSError):
                os.close(fd)
        self._master_fd = None
        self._slave_fd = None
        self.port = None

    def handle_command(self, command_line: str) -> bytes:
        line = command_line.strip()
        if not line:
            return b"ok"
        if line.startswith("{"):
            return self._handle_typed_command(line)
        return self._handle_legacy_command(line)

    def _handle_legacy_command(self, command_line: str) -> bytes:
        line = command_line.strip()
        upper = line.upper()
        if upper in {"RESET", "TRIGGER"}:
            return f"{upper.lower()} ok".encode()
        if upper in {"PING", "HELLO"}:
            return b"pong"

        params = parse_glitch_params(line)
        result = self._hardware.execute(params)
        if self.response_delay_s > 0:
            time.sleep(self.response_delay_s)
        return result.serial_output

    def _handle_typed_command(self, command_line: str) -> bytes:
        payload = json.loads(command_line)
        if not isinstance(payload, dict):
            raise ValueError("typed command must be a JSON object")

        command = str(payload.get("command", "")).lower()
        if command == "hello":
            return json.dumps(
                {
                    "status": "ok",
                    "protocol": "autoglitch.v1",
                    "adapter_id": self.adapter_id,
                    "transport": "serial",
                    "identity": {"model": "mock-bridge", "seed": self.seed},
                    "capabilities": [
                        "glitch.execute",
                        "target.reset",
                        "target.trigger",
                        "healthcheck",
                    ],
                }
            ).encode("utf-8")
        if command == "capabilities":
            return json.dumps(
                {
                    "status": "ok",
                    "capabilities": [
                        "glitch.execute",
                        "target.reset",
                        "target.trigger",
                        "healthcheck",
                    ],
                }
            ).encode("utf-8")
        if command == "health":
            return json.dumps({"status": "ok", "ok": True}).encode("utf-8")
        if command == "reset":
            return json.dumps({"status": "ok", "message": "reset ok"}).encode("utf-8")
        if command == "trigger":
            return json.dumps({"status": "ok", "message": "trigger ok"}).encode("utf-8")
        if command == "execute":
            params = _parse_typed_params(payload)
            result = self._hardware.execute(params)
            if self.response_delay_s > 0:
                time.sleep(self.response_delay_s)
            return json.dumps(
                {
                    "status": "ok",
                    "serial_output": result.serial_output.decode("utf-8", errors="replace"),
                    "reset_detected": bool(result.reset_detected),
                    "error_code": result.error_code,
                }
            ).encode("utf-8")
        return json.dumps({"status": "error", "message": f"unknown command: {command}"}).encode("utf-8")

    def serve_once(self, timeout_s: float = 0.2) -> int:
        self.open_pty()
        assert self._master_fd is not None
        ready, _, _ = select.select([self._master_fd], [], [], timeout_s)
        if not ready:
            return 0

        chunk = os.read(self._master_fd, 4096)
        if not chunk:
            return 0
        self._buffer += chunk

        processed = 0
        while b"\n" in self._buffer:
            raw_line, self._buffer = self._buffer.split(b"\n", 1)
            line = raw_line.decode("utf-8", errors="replace").strip("\r")
            if not line:
                continue
            try:
                response = self.handle_command(line)
            except Exception as exc:
                response = f"err {type(exc).__name__}: {exc}".encode("utf-8", errors="replace")
            os.write(self._master_fd, response.rstrip(b"\n") + b"\n")
            processed += 1

        return processed

    def serve_forever(
        self,
        *,
        stop_event: threading.Event | None = None,
        duration_s: float | None = None,
        max_commands: int | None = None,
    ) -> int:
        stop_event = stop_event or threading.Event()
        started = time.monotonic()
        commands = 0

        while not stop_event.is_set():
            commands += self.serve_once(timeout_s=0.2)
            if duration_s is not None and (time.monotonic() - started) >= duration_s:
                break
            if max_commands is not None and commands >= max_commands:
                break

        return commands


def run_mock_bridge(
    *,
    seed: int = 42,
    response_delay_s: float = 0.0,
    duration_s: float | None = None,
    port_file: Path | None = None,
) -> None:
    bridge = MockGlitchBridge(seed=seed, response_delay_s=response_delay_s)
    try:
        port = bridge.open_pty()
        if port_file is not None:
            port_file.parent.mkdir(parents=True, exist_ok=True)
            port_file.write_text(port, encoding="utf-8")

        print(port, flush=True)
        bridge.serve_forever(duration_s=duration_s)
    finally:
        bridge.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AUTOGLITCH mock serial glitch bridge")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--response-delay-s", type=float, default=0.0)
    parser.add_argument("--duration-s", type=float, default=None)
    parser.add_argument("--port-file", default=None, help="optional file to store generated PTY path")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    port_file = Path(args.port_file) if args.port_file else None
    run_mock_bridge(
        seed=int(args.seed),
        response_delay_s=float(args.response_delay_s),
        duration_s=float(args.duration_s) if args.duration_s is not None else None,
        port_file=port_file,
    )


if __name__ == "__main__":
    main()
