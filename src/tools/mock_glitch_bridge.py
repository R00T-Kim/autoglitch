"""Software-only serial glitch bridge emulator.

This helper exposes a pseudo-terminal (PTY) that accepts the same line protocol used by
``SerialCommandHardware`` and returns mock responses. It enables serial-mode end-to-end
testing without physical glitch hardware.
"""
from __future__ import annotations

import argparse
import os
import pty
import select
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..hardware import MockHardware
from ..types import GlitchParameters


def parse_glitch_params(command_line: str) -> GlitchParameters:
    """Parse protocol line: ``GLITCH width=... offset=... voltage=... repeat=... ext_offset=...``."""
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


@dataclass
class MockGlitchBridge:
    """PTY-backed mock bridge server."""

    seed: int = 42
    response_delay_s: float = 0.0

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
            try:
                os.close(fd)
            except OSError:
                pass
        self._master_fd = None
        self._slave_fd = None
        self.port = None

    def handle_command(self, command_line: str) -> bytes:
        line = command_line.strip()
        upper = line.upper()
        if upper == "RESET":
            return b"reset ok"
        if upper == "TRIGGER":
            return b"trigger ok"

        params = parse_glitch_params(line)
        result = self._hardware.execute(params)
        if self.response_delay_s > 0:
            time.sleep(self.response_delay_s)
        return result.serial_output

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
        stop_event: Optional[threading.Event] = None,
        duration_s: Optional[float] = None,
        max_commands: Optional[int] = None,
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
