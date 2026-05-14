import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from vfobs.config import Settings
from vfobs.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN = "live-test-token"


def _run_alembic_upgrade(database_url: str):
    env = {
        "VFOBS_DATABASE_URL": database_url,
        "VFOBS_INGEST_TOKEN": "test",
        "VFOBS_APP_DB_PASSWORD": "testapppw",
        "PATH": "/usr/bin:/bin:" + str(REPO_ROOT / ".venv" / "bin"),
    }
    subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "alembic"), "upgrade", "head"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
async def live_app(vfobs_database_url):
    _run_alembic_upgrade(vfobs_database_url)
    settings = Settings(
        database_url=vfobs_database_url,  # type: ignore[arg-type]
        ingest_token=SecretStr(TOKEN),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.mark.integration
async def test_post_event_persists_and_sets_created_at(live_app, pg_url):
    payload = {
        "type": "task.state_changed",
        "v": 1,
        "workgraph_id": "wg_live",
        "task_id": "t_live",
        "source": "live-test",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"from_status": "todo", "to_status": "doing"},
    }
    transport = ASGITransport(app=live_app)
    before = datetime.now(UTC)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/events", json=payload, headers={"Authorization": f"Bearer {TOKEN}"}
        )
    assert resp.status_code == 201
    eid = resp.json()["id"]
    assert isinstance(eid, int) and eid > 0

    # Read directly from Postgres to confirm server-time audit (created_at)
    engine = sa.create_engine(pg_url)
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT type, workgraph_id, task_id, data, created_at FROM vfobs.events WHERE id = :id"),
            {"id": eid},
        ).mappings().one()
    assert row["type"] == "task.state_changed"
    assert row["workgraph_id"] == "wg_live"
    assert row["task_id"] == "t_live"
    assert row["data"]["from_status"] == "todo"
    assert row["data"]["to_status"] == "doing"
    delta = row["created_at"] - before
    assert timedelta(seconds=-1) <= delta <= timedelta(seconds=10)


@pytest.mark.integration
async def test_live_unauthorized_returns_401(live_app):
    payload = {
        "type": "task.heartbeat",
        "v": 1,
        "workgraph_id": "wg_live",
        "task_id": "t_live",
        "source": "live-test",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"at": datetime.now(UTC).isoformat()},
    }
    transport = ASGITransport(app=live_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/events", json=payload)
    assert resp.status_code == 401
