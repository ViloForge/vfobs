from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from vfobs.api.auth import StaticTokenAuth
from vfobs.api.events import enricher, run_pipeline, storer
from vfobs.config import Settings
from vfobs.events import EventFactory
from vfobs.main import create_app
from vfobs.repositories import InMemoryEventRepository

TEST_TOKEN = "testtok"


@pytest.fixture
def app_with_inmemory():
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr(TEST_TOKEN),
    )
    repo = InMemoryEventRepository()
    auth = StaticTokenAuth(settings)
    app = create_app(settings, event_repo=repo, ingest_auth=auth)
    # bypass lifespan (it would try to connect to Postgres); manually
    # set state as if lifespan ran.
    app.state.engine = None
    return app, repo


def _sample_payload(workgraph_id="wg_u", task_id="t_u"):
    return {
        "type": "task.state_changed",
        "v": 1,
        "workgraph_id": workgraph_id,
        "task_id": task_id,
        "source": "unit-test",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"from_status": "todo", "to_status": "doing"},
    }


@pytest.mark.unit
def test_post_valid_event_returns_201_and_id(app_with_inmemory):
    app, repo = app_with_inmemory
    with TestClient(app) as client:
        resp = client.post(
            "/events",
            json=_sample_payload(),
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
    assert resp.status_code == 201
    assert resp.json() == {"id": 1}


@pytest.mark.unit
def test_post_second_event_returns_id_2(app_with_inmemory):
    app, repo = app_with_inmemory
    with TestClient(app) as client:
        client.post(
            "/events",
            json=_sample_payload(),
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        resp = client.post(
            "/events",
            json=_sample_payload(),
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
    assert resp.status_code == 201
    assert resp.json() == {"id": 2}


@pytest.mark.unit
def test_post_missing_token_returns_401(app_with_inmemory):
    app, _ = app_with_inmemory
    with TestClient(app) as client:
        resp = client.post("/events", json=_sample_payload())
    assert resp.status_code == 401


@pytest.mark.unit
def test_post_wrong_token_returns_401(app_with_inmemory):
    app, _ = app_with_inmemory
    with TestClient(app) as client:
        resp = client.post(
            "/events",
            json=_sample_payload(),
            headers={"Authorization": "Bearer wrong"},
        )
    assert resp.status_code == 401


@pytest.mark.unit
def test_post_bad_event_shape_returns_422(app_with_inmemory):
    app, _ = app_with_inmemory
    with TestClient(app) as client:
        resp = client.post(
            "/events",
            json={"type": "task.state_changed", "junk": True},
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
    assert resp.status_code == 422


@pytest.mark.unit
def test_post_unknown_event_type_returns_422(app_with_inmemory):
    app, _ = app_with_inmemory
    bad = _sample_payload()
    bad["type"] = "task.nonexistent"
    with TestClient(app) as client:
        resp = client.post(
            "/events",
            json=bad,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
    assert resp.status_code == 422


# ---- Pipeline ordering + Enricher no-op fingerprint ------------------------


@pytest.mark.unit
async def test_enricher_returns_event_unchanged():
    e = EventFactory.task_heartbeat(
        workgraph_id="wg", task_id="t", source="u",
        timestamp=datetime.now(UTC),
    )
    out = await enricher(e, context={})
    assert out is e or out == e  # no-op (identity or equality)


@pytest.mark.unit
async def test_pipeline_runs_enricher_before_storer():
    """A stub Enricher records its call order; if it raises, Storer is
    never reached — Chain of Responsibility short-circuit semantics."""
    repo = InMemoryEventRepository()
    calls: list[str] = []

    async def stub_enricher(event, context):
        calls.append("enricher")
        return event

    async def real_storer(event, context):
        calls.append("storer")
        return await storer(event, context)

    e = EventFactory.task_heartbeat(
        workgraph_id="wg", task_id="t", source="u",
        timestamp=datetime.now(UTC),
    )
    await run_pipeline(e, {"repo": repo}, pipeline=[stub_enricher, real_storer])
    assert calls == ["enricher", "storer"]


@pytest.mark.unit
async def test_pipeline_short_circuits_on_enricher_exception():
    repo = InMemoryEventRepository()

    async def failing_enricher(event, context):
        raise RuntimeError("boom")

    async def real_storer(event, context):
        return await storer(event, context)

    e = EventFactory.task_heartbeat(
        workgraph_id="wg", task_id="t", source="u",
        timestamp=datetime.now(UTC),
    )
    with pytest.raises(RuntimeError):
        await run_pipeline(e, {"repo": repo}, pipeline=[failing_enricher, real_storer])
    assert await repo.get_by_id(1) is None  # storer never reached
