"""Emitter — fire-and-forget event delivery to vfobs.

Load-bearing contract (plan §D3, symmetric to vfobs read-side
D-T0-1 "degradable"): observability is NEVER on the caller's
critical path. `emit()` is sync, O(1), and never raises. All I/O
happens on a single background drain task with a bounded per-POST
timeout. A down/slow/5xx vfobs cannot raise, block, or
unboundedly slow the caller.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import time
from abc import ABC, abstractmethod

import httpx

from vfobs_sdk.events import Event

logger = logging.getLogger("vfobs_sdk.emitter")


class Emitter(ABC):
    @abstractmethod
    def emit(self, event: Event) -> None:
        """Enqueue an event for delivery. MUST be O(1) and MUST NOT
        raise — ever."""

    async def aclose(self) -> None:  # pragma: no cover - default no-op
        return None


class NullEmitter(Emitter):
    """No-op. Selected when emission is disabled/unconfigured — the
    caller behaves exactly as if vfobs did not exist."""

    def emit(self, event: Event) -> None:
        return None


class BufferingEmitter(Emitter):
    """Test substitute — records emitted events in order, no I/O."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class HttpEmitter(Emitter):
    def __init__(
        self,
        url: str,
        token: str,
        *,
        timeout: float = 2.0,
        queue_max: int = 1000,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url.rstrip("/") + "/events"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._timeout = timeout
        self._q: collections.deque[Event] = collections.deque(
            maxlen=queue_max
        )  # maxlen => drop-oldest on overflow, never raises
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self._wake = asyncio.Event()
        self._closed = False
        self._drain: asyncio.Task | None = None
        self._last_warn = 0.0
        self._warn_every = 60.0

    def _ensure_drain(self) -> None:
        if self._drain is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop yet; drain starts on a later emit/aclose
        self._drain = loop.create_task(self._run())

    def emit(self, event: Event) -> None:
        try:
            self._q.append(event)  # O(1), bounded, never raises
            self._wake.set()
            self._ensure_drain()
        except Exception:  # defensive: emit must never raise
            pass

    def _warn(self, exc: Exception) -> None:
        now = time.monotonic()
        if now - self._last_warn >= self._warn_every:
            self._last_warn = now
            logger.warning(
                "vfobs emit delivery failing (rate-limited log): %r", exc
            )

    async def _run(self) -> None:
        while not self._closed or self._q:
            if not self._q:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=1.0)
                except TimeoutError:
                    continue
            try:
                event = self._q.popleft()
            except IndexError:
                continue
            try:
                await self._http.post(
                    self._url,
                    json=event.model_dump(mode="json"),
                    headers=self._headers,
                    timeout=self._timeout,
                )
            except Exception as exc:  # network/4xx-raise/5xx/timeout
                self._warn(exc)  # never propagates

    async def aclose(self) -> None:
        self._closed = True
        self._wake.set()
        if self._drain is not None:
            try:
                await asyncio.wait_for(self._drain, timeout=self._timeout + 1)
            except (TimeoutError, asyncio.CancelledError):
                self._drain.cancel()
        await self._http.aclose()


def make_emitter(
    *,
    enabled: bool,
    url: str | None,
    token: str | None,
    timeout: float = 2.0,
    queue_max: int = 1000,
) -> Emitter:
    """Factory: returns a NullEmitter unless emission is explicitly
    enabled AND configured. The default path is therefore a no-op —
    turning emission on is a config flip, never a code change."""
    if enabled and url and token:
        return HttpEmitter(
            url, token, timeout=timeout, queue_max=queue_max
        )
    return NullEmitter()
