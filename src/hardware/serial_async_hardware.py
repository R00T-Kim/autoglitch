"""Async serial-based hardware adapter."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Tuple

from ..types import GlitchParameters, RawResult

AsyncConnectionFactory = Callable[[str, int, float], Awaitable[Tuple[Any, Any]]]


async def _default_open_connection(port: str, baudrate: int, timeout: float) -> Tuple[Any, Any]:
    try:
        import serial_asyncio
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime env
        raise RuntimeError("pyserial-asyncio is required for async serial mode") from exc

    return await asyncio.wait_for(
        serial_asyncio.open_serial_connection(url=port, baudrate=baudrate),
        timeout=timeout,
    )


@dataclass
class AsyncSerialCommandHardware:
    """Async serial command adapter using the same text protocol as sync mode."""

    port: str
    baudrate: int = 115200
    timeout: float = 1.0
    command_template: str = (
        "GLITCH width={width:.3f} offset={offset:.3f} "
        "voltage={voltage:.3f} repeat={repeat:d} ext_offset={ext_offset:.3f}"
    )
    reset_command: str = ""
    trigger_command: str = ""
    connection_factory: Optional[AsyncConnectionFactory] = None

    def connect(self) -> None:
        """Kept for API parity with sync adapter."""
        return None

    def disconnect(self) -> None:
        """Kept for API parity with sync adapter."""
        return None

    def execute(self, params: GlitchParameters) -> RawResult:
        start = time.perf_counter()
        response = self._run_coroutine(self._execute_once(params))
        response_time = time.perf_counter() - start

        lowered = response.lower()
        reset_detected = (not response) or (b"reset" in lowered) or (b"reboot" in lowered)
        error_code = 1 if any(token in lowered for token in (b"err", b"fault", b"exception", b"panic")) else None

        return RawResult(
            serial_output=response,
            response_time=float(response_time),
            reset_detected=reset_detected,
            error_code=error_code,
        )

    async def _execute_once(self, params: GlitchParameters) -> bytes:
        factory = self.connection_factory or _default_open_connection
        reader, writer = await factory(self.port, self.baudrate, self.timeout)
        try:
            if self.reset_command:
                await self._write_line(writer, self.reset_command)

            payload = self.command_template.format(
                width=params.width,
                offset=params.offset,
                voltage=params.voltage,
                repeat=params.repeat,
                ext_offset=params.ext_offset,
            )
            await self._write_line(writer, payload)

            if self.trigger_command:
                await self._write_line(writer, self.trigger_command)

            raw = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
            return bytes(raw).strip()
        finally:
            close = getattr(writer, "close", None)
            if callable(close):
                close()
            wait_closed = getattr(writer, "wait_closed", None)
            if callable(wait_closed):
                try:
                    await wait_closed()
                except Exception:  # pragma: no cover - defensive close
                    pass

    async def _write_line(self, writer: Any, message: str) -> None:
        payload = message.rstrip("\n").encode("utf-8") + b"\n"
        write = getattr(writer, "write", None)
        if not callable(write):
            raise RuntimeError("writer object has no write()")
        write(payload)
        drain = getattr(writer, "drain", None)
        if callable(drain):
            await drain()

    @staticmethod
    def _run_coroutine(coro: Awaitable[bytes]) -> bytes:
        try:
            return asyncio.run(coro)
        except RuntimeError:
            # Fallback for environments with an already-running event loop.
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
