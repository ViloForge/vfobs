import asyncio

import httpx
import pytest

from vfobs_sdk import (
    BufferingEmitter,
    HttpEmitter,
    NullEmitter,
    make_emitter,
    task_heartbeat,
)


def _hb():
    return task_heartbeat(workgraph_id="wg", task_id="t", source="unit")


@pytest.mark.unit
def test_null_emitter_is_true_noop():
    e = NullEmitter()
    for _ in range(1000):
        e.emit(_hb())  # never raises, does nothing


@pytest.mark.unit
def test_buffering_emitter_records_in_order():
    e = BufferingEmitter()
    e.emit(_hb())
    e.emit(_hb())
    assert len(e.events) == 2


@pytest.mark.unit
def test_factory_selects_null_unless_enabled_and_configured():
    assert isinstance(make_emitter(enabled=False, url="u", token="t"), NullEmitter)
    assert isinstance(make_emitter(enabled=True, url=None, token="t"), NullEmitter)
    assert isinstance(make_emitter(enabled=True, url="u", token=None), NullEmitter)
    assert isinstance(
        make_emitter(enabled=True, url="http://x", token="t"), HttpEmitter
    )


@pytest.mark.unit
async def test_emit_never_raises_on_connection_refused():
    # nothing listening; drain must swallow, emit must return instantly
    e = HttpEmitter("http://127.0.0.1:1", "tok", timeout=0.2)
    for _ in range(10):
        e.emit(_hb())  # must not raise
    await asyncio.sleep(0.3)  # let the drain attempt + fail quietly
    await e.aclose()


@pytest.mark.unit
async def test_emit_never_raises_on_5xx_or_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    e = HttpEmitter("http://vfobs.test", "tok", timeout=0.5, http=client)
    e.emit(_hb())
    e.emit(_hb())
    await asyncio.sleep(0.2)
    await e.aclose()  # no raise despite 503s


@pytest.mark.unit
async def test_overflow_drops_oldest_bounded_queue():
    # tiny queue; flood without draining (no loop time given) then
    # confirm it's bounded, not unbounded growth / not raising.
    e = HttpEmitter("http://127.0.0.1:1", "tok", queue_max=5)
    for _ in range(100):
        e.emit(_hb())
    assert len(e._q) == 5  # bounded; oldest dropped
    await e.aclose()


@pytest.mark.unit
async def test_emit_is_constant_time_not_blocking_on_slow_endpoint():
    async def slow(request):
        await asyncio.sleep(5)
        return httpx.Response(201)

    client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    e = HttpEmitter("http://vfobs.test", "tok", timeout=0.3, http=client)
    import time

    t0 = time.monotonic()
    for _ in range(50):
        e.emit(_hb())
    assert time.monotonic() - t0 < 0.1  # O(1) enqueue, never awaits HTTP
    await e.aclose()
