"""Integration: WG2-T2 endpoints against a real Postgres repo + a
fake vtaskforge ASGI app. Mirrors the WG1 live-endpoint pattern
(lifespan_context + ASGITransport + AsyncClient, single event loop)
so asyncpg stays on one loop. Seeds events, hits /workgraphs/<id>
and /tasks/<id>/events, asserts payload matches seeded data.
"""

import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from vfobs.adapters.vtf import VtfClient
from vfobs.api.read_auth import Principal, StaticPrincipalAuth
from vfobs.config import Settings
from vfobs.events import EventFactory
from vfobs.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic_upgrade(database_url: str) -> None:
    subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "alembic"), "upgrade", "head"],
        cwd=str(REPO_ROOT),
        env={
            "VFOBS_DATABASE_URL": database_url,
            "VFOBS_INGEST_TOKEN": "test",
            "VFOBS_APP_DB_PASSWORD": "testapppw",
            "PATH": "/usr/bin:/bin:" + str(REPO_ROOT / ".venv" / "bin"),
        },
        capture_output=True,
        text=True,
        check=True,
    )


def _fake_vtf() -> FastAPI:
    # Grounded contract: workgraph == milestone (/v2/milestones/),
    # real serializer fields (no kind/target_repos/tags).
    app = FastAPI()

    @app.get("/v2/milestones/{mid}/")
    def ms(mid: str) -> dict:
        return {"id": mid, "name": "Live MS", "status": "doing",
                "order": 0}

    @app.get("/v2/tasks/{tid}/")
    def task(tid: str) -> dict:
        return {"id": tid, "title": "Live Task", "status": "doing"}

    return app


@pytest.mark.integration
async def test_reads_live_compose_real_pg_and_fake_vtf(vfobs_database_url):
    _run_alembic_upgrade(vfobs_database_url)
    settings = Settings(
        database_url=vfobs_database_url,  # type: ignore[arg-type]
        ingest_token=SecretStr("x"),
        vtaskforge_url="http://vtf.local",  # type: ignore[arg-type]
    )
    vtf = VtfClient(
        settings,
        http=httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_fake_vtf()),
            base_url="http://vtf.local",
        ),
    )
    # Inject read_auth + vtf_client (lifespan skips resolving them);
    # let lifespan build the real PostgresEventRepository in-loop.
    app = create_app(
        settings,
        read_auth=StaticPrincipalAuth(Principal(user_id="op")),
        vtf_client=vtf,
    )
    # Unique ids — the testcontainers Postgres is session-scoped and
    # shared across every integration test file (WG1's live test also
    # uses wg_live/t_live), so event_count assertions need isolation.
    wgid = f"wg_live_{uuid.uuid4().hex[:8]}"
    tid = f"t_live_{uuid.uuid4().hex[:8]}"
    async with app.router.lifespan_context(app):
        repo = app.state.event_repo
        seeded = []
        for _ in range(5):
            seeded.append(
                await repo.store(
                    EventFactory.task_state_changed(
                        workgraph_id=wgid, task_id=tid,
                        source="int", from_status="todo", to_status="doing",
                        timestamp=datetime.now(UTC),
                    )
                )
            )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            wg = (
                await client.get(
                    f"/workgraphs/{wgid}",
                    headers={"Authorization": "Bearer t"},
                )
            ).json()
            ev = (
                await client.get(
                    f"/tasks/{tid}/events?limit=3",
                    headers={"Authorization": "Bearer t"},
                )
            ).json()

    assert wg["vtf"]["name"] == "Live MS"
    assert wg["vfobs"]["event_count"] == 5
    assert wg["vfobs"]["last_event_id"] == seeded[-1]
    assert [e["id"] for e in ev["events"]] == seeded[:3]
    assert ev["next_from_id"] == seeded[2] + 1
    assert ev["events"][0]["event"]["workgraph_id"] == wgid
