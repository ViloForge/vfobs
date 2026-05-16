"""Integration: HttpEmitter against a real ASGI vfobs-like
endpoint (httpx ASGITransport — a single shared event loop). Proves
round-trip delivery AND the fail-safe (5xx → caller unaffected).
"""

import asyncio

import httpx
import pytest
from fastapi import FastAPI, Request

from vfobs_sdk import HttpEmitter, task_heartbeat, task_state_changed
from vfobs_sdk.events import ExecutionSummary


def _vfobs_like(received: list) -> FastAPI:
    app = FastAPI()

    @app.post("/events")
    async def events(request: Request):
        received.append(await request.json())
        return {"id": len(received)}

    return app


@pytest.mark.integration
async def test_emitter_round_trips_two_event_types():
    received: list = []
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_vfobs_like(received)),
        base_url="http://vfobs.test",
    )
    e = HttpEmitter("http://vfobs.test", "tok", http=client)
    e.emit(task_heartbeat(workgraph_id="wg", task_id="t", source="int"))
    e.emit(
        task_state_changed(
            workgraph_id="wg", task_id="t", source="int",
            from_status="doing", to_status="done",
            execution_summary=ExecutionSummary(
                num_turns=3, total_tokens=100, cost_usd=0.5
            ),
        )
    )
    for _ in range(50):
        if len(received) == 2:
            break
        await asyncio.sleep(0.05)
    await e.aclose()

    assert len(received) == 2
    types = {r["type"] for r in received}
    assert types == {"task.heartbeat", "task.state_changed"}
    sc = next(r for r in received if r["type"] == "task.state_changed")
    assert sc["data"]["execution_summary"]["cost_usd"] == 0.5
    assert "Authorization" not in sc  # header, not body (sanity)


@pytest.mark.integration
async def test_caller_unaffected_when_vfobs_returns_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    e = HttpEmitter("http://vfobs.test", "tok", timeout=0.5, http=client)

    import time

    t0 = time.monotonic()
    for _ in range(20):
        e.emit(task_heartbeat(workgraph_id="wg", task_id="t", source="i"))
    enqueue_elapsed = time.monotonic() - t0
    await asyncio.sleep(0.3)  # drain attempts + fails quietly
    await e.aclose()

    assert enqueue_elapsed < 0.05  # caller never paid the 500s
