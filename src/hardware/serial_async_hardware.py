"""Async serial-based hardware adapter."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
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


class AsyncSerialConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


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
    keep_open: bool = True
    reconnect_attempts: int = 2
    reconnect_backoff_s: float = 0.05
    connection_factory: Optional[AsyncConnectionFactory] = None

    def __post_init__(self) -> None:
        self._reader: Any | None = None
        self._writer: Any | None = None
        self._state = AsyncSerialConnectionState.DISCONNECTED

    @property
    def connection_state(self) -> str:
        return self._state.value

    def connect(self) -> None:
        """Open persistent serial connection if not already connected."""
        self._run_coroutine(self._ensure_connection())

    def disconnect(self) -> None:
        """Close serial connection and reset state."""
        self._run_coroutine(self._disconnect_async())

    def execute(self, params: GlitchParameters) -> RawResult:
        start = time.perf_counter()
        response = self._run_coroutine(self._execute_with_reconnect(params))
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

    async def _execute_with_reconnect(self, params: GlitchParameters) -> bytes:
        max_attempts = max(1, int(self.reconnect_attempts) + 1)
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            try:
                await self._ensure_connection(reconnecting=attempt > 0)
                assert self._reader is not None and self._writer is not None
                response = await self._execute_once(params, reader=self._reader, writer=self._writer)
                if not self.keep_open:
                    await self._disconnect_async()
                return response
            except Exception as exc:
                last_error = exc
                await self._disconnect_async()
                if attempt >= max_attempts - 1:
                    break

                wait_s = max(0.0, float(self.reconnect_backoff_s)) * (2**attempt)
                if wait_s > 0:
                    await asyncio.sleep(wait_s)

        if last_error is None:
            raise RuntimeError("async serial execution failed")
        raise RuntimeError(
            f"async serial execution failed after {max_attempts} attempts"
        ) from last_error

    async def _execute_once(self, params: GlitchParameters, *, reader: Any, writer: Any) -> bytes:
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

    async def _ensure_connection(self, reconnecting: bool = False) -> None:
        if self._reader is not None and self._writer is not None:
            self._state = AsyncSerialConnectionState.CONNECTED
            return

        self._state = (
            AsyncSerialConnectionState.RECONNECTING
            if reconnecting
            else AsyncSerialConnectionState.CONNECTING
        )

        factory = self.connection_factory or _default_open_connection
        try:
            reader, writer = await factory(self.port, self.baudrate, self.timeout)
        except Exception:
            self._state = AsyncSerialConnectionState.DISCONNECTED
            raise

        self._reader = reader
        self._writer = writer
        self._state = AsyncSerialConnectionState.CONNECTED

    async def _disconnect_async(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None

        if writer is not None:
            close = getattr(writer, "close", None)
            if callable(close):
                close()
            wait_closed = getattr(writer, "wait_closed", None)
            if callable(wait_closed):
                try:
                    await wait_closed()
                except Exception:  # pragma: no cover - defensive close
                    pass

        self._state = AsyncSerialConnectionState.DISCONNECTED

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
