from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from vfobs.api.cost import ByAgent, ByWorkgraph
from vfobs.api.read_auth import Principal, StaticPrincipalAuth, VtfTokenAuth
from vfobs.config import Settings
from vfobs.events import EventFactory
from vfobs.events.namespaces.task import ExecutionSummary
from vfobs.main import create_app
from vfobs.repositories import InMemoryEventRepository

H = {"Authorization": "Bearer t"}


class _Vtf:
    async def aclose(self):
        pass


def _sc(wg, task, *, agent=None, es=None, to="done"):
    return EventFactory.task_state_changed(
        workgraph_id=wg, task_id=task, source="u",
        from_status="doing", to_status=to, execution_summary=es,
        timestamp=datetime.now(UTC),
        **({"agent_id": agent} if agent else {}),
    )


def _app(repo, read_auth=None):
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
            ingest_token=SecretStr("x"),
            vtaskforge_url="http://vtf.test",  # type: ignore[arg-type]
        ),
        event_repo=repo,
        read_auth=read_auth or StaticPrincipalAuth(Principal(user_id="op")),
        vtf_client=_Vtf(),
    )
    app.state.engine = None
    return app


@pytest.mark.unit
async def test_strategy_empty_is_zeros():
    repo = InMemoryEventRepository()
    cs = await ByWorkgraph("nope").compute(repo)
    assert cs.total_cost_usd == 0.0 and cs.task_count == 0


@pytest.mark.unit
async def test_strategy_sums_excludes_inflight_handles_missing_fields():
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg", "t1", es=ExecutionSummary(
        num_turns=2, total_tokens=50, cost_usd=0.5)))
    await repo.store(_sc("wg", "t2", es=ExecutionSummary(cost_usd=0.25)))
    await repo.store(_sc("wg", "t3", to="doing", es=None))  # in-flight
    cs = await ByWorkgraph("wg").compute(repo)
    assert cs.total_cost_usd == pytest.approx(0.75)
    assert cs.total_tokens == 50  # t2 missing -> 0, no NaN
    assert cs.task_count == 2


@pytest.mark.unit
async def test_strategy_f2_reworked_task_counted_once():
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg", "t_rw", es=ExecutionSummary(cost_usd=0.1)))
    await repo.store(_sc("wg", "t_rw", es=ExecutionSummary(cost_usd=0.4)))
    cs = await ByWorkgraph("wg").compute(repo)
    assert cs.task_count == 1 and cs.total_cost_usd == pytest.approx(0.4)


@pytest.mark.unit
async def test_by_agent_strategy_scope():
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg", "t1", agent="ag_x",
                         es=ExecutionSummary(cost_usd=1.0)))
    await repo.store(_sc("wg", "t2", agent="ag_y",
                         es=ExecutionSummary(cost_usd=2.0)))
    cs = await ByAgent("ag_x").compute(repo)
    assert cs.total_cost_usd == pytest.approx(1.0) and cs.task_count == 1


@pytest.mark.unit
async def test_cost_endpoints_happy_and_shape():
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg_e", "t1", agent="ag_e",
                         es=ExecutionSummary(num_turns=3, total_tokens=99,
                                             cost_usd=1.5)))
    with TestClient(_app(repo)) as c:
        w = c.get("/workgraphs/wg_e/cost", headers=H).json()
        a = c.get("/agents/ag_e/cost", headers=H).json()
    assert w["v"] == 1 and w["workgraph_id"] == "wg_e"
    assert w["summary"]["total_cost_usd"] == pytest.approx(1.5)
    assert w["summary"]["total_tokens"] == 99
    assert a["agent_id"] == "ag_e"
    assert a["summary"]["total_cost_usd"] == pytest.approx(1.5)


@pytest.mark.unit
async def test_cost_404_when_scope_has_no_events():
    with TestClient(_app(InMemoryEventRepository())) as c:
        assert c.get("/workgraphs/ghost/cost", headers=H).status_code == 404
        assert c.get("/agents/ghost/cost", headers=H).status_code == 404


@pytest.mark.unit
async def test_cost_requires_auth():
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg_a", "t", es=ExecutionSummary(cost_usd=1.0)))
    app = _app(repo, read_auth=VtfTokenAuth(_Vtf()))  # type: ignore[arg-type]
    with TestClient(app) as c:
        assert c.get("/workgraphs/wg_a/cost").status_code == 401
        assert c.get("/agents/x/cost").status_code == 401
