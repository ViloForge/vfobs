"""Integration: ReadClient + watcher rules against a REAL vfobs
served over real HTTP (uvicorn on an ephemeral port, InMemory repo
seeded). Proves the watcher's verdicts against the actual WG2 wire
shape for the three outcomes the use case cares about.
"""

import socket
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
import uvicorn

from vfobs.api.read_auth import Principal, StaticPrincipalAuth
from vfobs.config import Settings
from vfobs.events import EventFactory
from vfobs.events.namespaces.task import ExecutionSummary  # noqa: F401
from vfobs.main import create_app
from vfobs.repositories import InMemoryEventRepository
from pydantic import SecretStr

from vfobs_sdk.read_client import ReadClient
from vfobs_sdk.watch import WatchState, default_rules, evaluate


class _Vtf:
    async def aclose(self): ...


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _serve(app, port):
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(cfg)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return server
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("vfobs test server did not start")


@pytest.fixture
def live_url():
    repo = InMemoryEventRepository()
    base = datetime.now(UTC) - timedelta(seconds=400)

    def at(delta):
        return base + timedelta(seconds=delta)

    import asyncio

    async def seed():
        await repo.store(EventFactory.task_claimed(
            workgraph_id="wg", task_id="h", source="s",
            claimed_by_agent_id="a", timestamp=at(0)))
        await repo.store(EventFactory.task_heartbeat(
            workgraph_id="wg", task_id="h", source="s", timestamp=at(395)))
        await repo.store(EventFactory.harness_turn_completed(
            workgraph_id="wg", task_id="h", source="s",
            turn_number=2, timestamp=at(396)))
        # stalled task s: claimed + FRESH heartbeats but harness 380s ago
        await repo.store(EventFactory.task_claimed(
            workgraph_id="wg", task_id="s", source="s",
            claimed_by_agent_id="a", timestamp=at(0)))
        await repo.store(EventFactory.harness_turn_started(
            workgraph_id="wg", task_id="s", source="s",
            turn_number=1, model="m", timestamp=at(15)))
        await repo.store(EventFactory.task_heartbeat(
            workgraph_id="wg", task_id="s", source="s", timestamp=at(398)))

    asyncio.run(seed())

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr("x"), vtaskforge_url="http://v",  # type: ignore[arg-type]
    )
    app = create_app(
        settings, event_repo=repo,
        read_auth=StaticPrincipalAuth(Principal(user_id="op")),
        vtf_client=_Vtf(),
    )
    app.state.engine = None
    port = _free_port()
    server = _serve(app, port)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


@pytest.mark.integration
def test_healthy_task_is_ok(live_url):
    c = ReadClient(live_url, "tok")
    ev = c.task_events("h")
    c.close()
    st = WatchState.from_events(
        ev, now=datetime.now(UTC), task_timeout_s=3600
    )
    assert evaluate(st, default_rules(stall_s=60, crash_s=120, fraction=0.8)).level == "OK"


@pytest.mark.integration
def test_stalled_task_is_flagged(live_url):
    c = ReadClient(live_url, "tok")
    ev = c.task_events("s")
    c.close()
    st = WatchState.from_events(
        ev, now=datetime.now(UTC), task_timeout_s=36000
    )
    v = evaluate(st, default_rules(stall_s=60, crash_s=600, fraction=0.8))
    assert v.level == "STALLED"


@pytest.mark.integration
def test_near_timeout_task_is_flagged(live_url):
    c = ReadClient(live_url, "tok")
    ev = c.task_events("h")
    c.close()
    # tiny timeout so 'h' (claimed 400s ago) is past 80%
    st = WatchState.from_events(ev, now=datetime.now(UTC), task_timeout_s=100)
    v = evaluate(st, default_rules(stall_s=600, crash_s=600, fraction=0.8))
    assert v.level == "APPROACHING_TIMEOUT"
