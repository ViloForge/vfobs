from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from vfobs.api.read_auth import Principal, StaticPrincipalAuth
from vfobs.config import Settings
from vfobs.events import EventFactory
from vfobs.main import create_app
from vfobs.repositories import InMemoryEventRepository

H = {"Authorization": "Bearer t"}


class FakeVtf:
    async def aclose(self):
        pass


def _settings():
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr("x"),
        vtaskforge_url="http://vtf.test",  # type: ignore[arg-type]
    )


def _ev(wg="wg", task="t", agent=None, type_ns="task"):
    if type_ns == "task":
        return EventFactory.task_state_changed(
            workgraph_id=wg, task_id=task, source="u",
            from_status="todo", to_status="doing",
            timestamp=datetime.now(UTC),
            **({"agent_id": agent} if agent else {}),
        )
    return EventFactory.harness_tool_call(
        workgraph_id=wg, task_id=task, source="u", turn_number=1,
        tool_name="Bash", timestamp=datetime.now(UTC),
        **({"agent_id": agent} if agent else {}),
    )


def _app(repo):
    app = create_app(
        _settings(), event_repo=repo,
        read_auth=StaticPrincipalAuth(Principal(user_id="op")),
        vtf_client=FakeVtf(),
    )
    app.state.engine = None
    return app


@pytest.mark.unit
async def test_filter_and_combine_and_filter_applied():
    repo = InMemoryEventRepository()
    await repo.store(_ev("wg_a", "t_1", agent="ag_1"))
    hit = await repo.store(_ev("wg_a", "t_2", agent="ag_2"))
    await repo.store(_ev("wg_b", "t_3", agent="ag_2"))
    with TestClient(_app(repo)) as c:
        b = c.get(
            "/events?workgraph_id=wg_a&agent_id=ag_2", headers=H
        ).json()
    assert [e["id"] for e in b["events"]] == [hit]
    assert b["events"][0]["event"]["workgraph_id"] == "wg_a"
    assert b["filter_applied"] == {
        "workgraph_id": "wg_a", "agent_id": "ag_2"
    }
    assert b["next_from_id"] is None  # partial page


@pytest.mark.unit
async def test_type_namespace_and_type_filters():
    repo = InMemoryEventRepository()
    await repo.store(_ev("wg", "t", type_ns="task"))
    await repo.store(_ev("wg", "t", type_ns="harness"))
    with TestClient(_app(repo)) as c:
        only_task = c.get("/events?type_namespace=task", headers=H).json()
        only_tc = c.get(
            "/events?type=harness.tool_call", headers=H
        ).json()
    assert len(only_task["events"]) == 1
    assert only_task["events"][0]["event"]["type"] == "task.state_changed"
    assert only_tc["events"][0]["event"]["type"] == "harness.tool_call"


@pytest.mark.unit
async def test_pagination_cursor_math():
    repo = InMemoryEventRepository()
    ids = [await repo.store(_ev("wg_p", "t_p")) for _ in range(5)]
    with TestClient(_app(repo)) as c:
        p1 = c.get("/events?workgraph_id=wg_p&limit=2", headers=H).json()
        assert [e["id"] for e in p1["events"]] == ids[:2]
        assert p1["next_from_id"] == ids[1] + 1
        p2 = c.get(
            f"/events?workgraph_id=wg_p&limit=2&from_id={p1['next_from_id']}",
            headers=H,
        ).json()
        assert [e["id"] for e in p2["events"]] == ids[2:4]


@pytest.mark.unit
async def test_unknown_param_is_422():
    with TestClient(_app(InMemoryEventRepository())) as c:
        r = c.get("/events?bogus=1", headers=H)
    assert r.status_code == 422


@pytest.mark.unit
async def test_bad_limit_and_from_id_are_422():
    with TestClient(_app(InMemoryEventRepository())) as c:
        assert c.get("/events?limit=5000", headers=H).status_code == 422
        assert c.get("/events?limit=0", headers=H).status_code == 422
        assert c.get("/events?from_id=-1", headers=H).status_code == 422
        assert c.get("/events?from_id=abc", headers=H).status_code == 422


@pytest.mark.unit
async def test_events_filter_requires_auth():
    from vfobs.api.read_auth import VtfTokenAuth

    repo = InMemoryEventRepository()
    app = create_app(
        _settings(), event_repo=repo,
        read_auth=VtfTokenAuth(FakeVtf()),  # type: ignore[arg-type]
        vtf_client=FakeVtf(),
    )
    app.state.engine = None
    with TestClient(app) as c:
        assert c.get("/events").status_code == 401
