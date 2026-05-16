from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from vfobs.adapters.dto import TaskMetadata, WorkgraphMetadata
from vfobs.adapters.vtf import VtfAuthError
from vfobs.api.read_auth import Principal, StaticPrincipalAuth, VtfTokenAuth
from vfobs.config import Settings
from vfobs.events import EventFactory
from vfobs.main import create_app
from vfobs.repositories import InMemoryEventRepository


class FakeVtf:
    def __init__(self, wg=None, task=None, raise_auth=False):
        self._wg = wg
        self._task = task
        self.raise_auth = raise_auth

    async def whoami(self, token):
        if self.raise_auth:
            raise VtfAuthError("bad")
        return None  # unused — StaticPrincipalAuth in most tests

    async def get_workgraph(self, wid, token):
        return self._wg if self._wg and self._wg.id == wid else None

    async def get_task(self, tid, token):
        return self._task if self._task and self._task.id == tid else None

    async def aclose(self):
        pass


def _settings():
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr("x"),
        vtaskforge_url="http://vtf.test",  # type: ignore[arg-type]
    )


def _ev(workgraph_id="wg_1", task_id="t_1"):
    return EventFactory.task_state_changed(
        workgraph_id=workgraph_id, task_id=task_id, source="unit",
        from_status="todo", to_status="doing", timestamp=datetime.now(UTC),
    )


def _app(repo, *, vtf, read_auth=None):
    auth = read_auth or StaticPrincipalAuth(Principal(user_id="op"))
    app = create_app(_settings(), event_repo=repo, read_auth=auth, vtf_client=vtf)
    app.state.engine = None
    return app


@pytest.mark.unit
async def test_get_workgraph_happy_path_composes_vtf_and_vfobs():
    repo = InMemoryEventRepository()
    eid = await repo.store(_ev("wg_1"))
    vtf = FakeVtf(wg=WorkgraphMetadata(id="wg_1", status="doing", name="M1"))
    with TestClient(_app(repo, vtf=vtf)) as c:
        r = c.get("/workgraphs/wg_1", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    b = r.json()
    assert b["v"] == 1 and b["workgraph_id"] == "wg_1"
    assert b["vtf"]["status"] == "doing" and b["vtf"]["name"] == "M1"
    assert b["vfobs"]["event_count"] == 1
    assert b["vfobs"]["last_event_id"] == eid
    assert b["vfobs"]["last_event_type"] == "task.state_changed"


@pytest.mark.unit
async def test_get_workgraph_404_when_vtf_none_and_no_events():
    vtf = FakeVtf(wg=None)
    with TestClient(_app(InMemoryEventRepository(), vtf=vtf)) as c:
        r = c.get("/workgraphs/ghost", headers={"Authorization": "Bearer t"})
    assert r.status_code == 404


@pytest.mark.unit
async def test_get_workgraph_asymmetric_events_only_returns_200_vtf_null():
    repo = InMemoryEventRepository()
    await repo.store(_ev("wg_only"))
    with TestClient(_app(repo, vtf=FakeVtf(wg=None))) as c:
        r = c.get("/workgraphs/wg_only", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    assert r.json()["vtf"] is None
    assert r.json()["vfobs"]["event_count"] == 1


@pytest.mark.unit
async def test_get_task_happy_and_404():
    repo = InMemoryEventRepository()
    await repo.store(_ev("wg_1", "t_1"))
    vtf = FakeVtf(task=TaskMetadata(id="t_1", status="doing", title="X"))
    with TestClient(_app(repo, vtf=vtf)) as c:
        ok = c.get("/tasks/t_1", headers={"Authorization": "Bearer t"})
        miss = c.get("/tasks/none", headers={"Authorization": "Bearer t"})
    assert ok.status_code == 200 and ok.json()["vtf"]["title"] == "X"
    assert miss.status_code == 404


@pytest.mark.unit
async def test_task_events_pagination_cursor():
    repo = InMemoryEventRepository()
    ids = [await repo.store(_ev("wg_p", "t_p")) for _ in range(5)]
    with TestClient(_app(repo, vtf=FakeVtf())) as c:
        p1 = c.get(
            "/tasks/t_p/events?limit=2", headers={"Authorization": "Bearer t"}
        ).json()
        assert [e["id"] for e in p1["events"]] == ids[:2]
        assert p1["next_from_id"] == ids[1] + 1
        assert p1["events"][0]["event"]["type"] == "task.state_changed"
        p2 = c.get(
            f"/tasks/t_p/events?limit=2&from_id={p1['next_from_id']}",
            headers={"Authorization": "Bearer t"},
        ).json()
        assert [e["id"] for e in p2["events"]] == ids[2:4]
        last = c.get(
            "/tasks/t_p/events?limit=100",
            headers={"Authorization": "Bearer t"},
        ).json()
        assert last["next_from_id"] is None  # partial page


@pytest.mark.unit
async def test_endpoints_require_auth_401_without_token():
    repo = InMemoryEventRepository()
    await repo.store(_ev("wg_1", "t_1"))
    # Real VtfTokenAuth -> verify(None) raises 401 before any whoami.
    app = _app(repo, vtf=FakeVtf(), read_auth=VtfTokenAuth(FakeVtf()))  # type: ignore[arg-type]
    with TestClient(app) as c:
        for path in ("/workgraphs/wg_1", "/tasks/t_1", "/tasks/t_1/events"):
            assert c.get(path).status_code == 401
