"""Integration: GET /events?filter=... against real Postgres.
Seeds events across workgraphs/types/agents, exercises filter
combinations + from_id cursor pagination. WG1 single-loop pattern;
uuid-namespaced ids (shared session PG container).
"""

import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from vfobs.api.read_auth import Principal, StaticPrincipalAuth
from vfobs.config import Settings
from vfobs.events import EventFactory
from vfobs.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic(database_url: str) -> None:
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


class _Vtf:
    async def aclose(self):
        pass


@pytest.mark.integration
async def test_events_filter_live(vfobs_database_url):
    _alembic(vfobs_database_url)
    ns = uuid.uuid4().hex[:8]
    wg1, wg2, wg3 = f"wg1_{ns}", f"wg2_{ns}", f"wg3_{ns}"
    settings = Settings(
        database_url=vfobs_database_url,  # type: ignore[arg-type]
        ingest_token=SecretStr("x"),
        vtaskforge_url="http://vtf.local",  # type: ignore[arg-type]
    )
    app = create_app(
        settings,
        read_auth=StaticPrincipalAuth(Principal(user_id="op")),
        vtf_client=_Vtf(),
    )
    async with app.router.lifespan_context(app):
        repo = app.state.event_repo

        async def sc(wg, task, agent):
            return await repo.store(
                EventFactory.task_state_changed(
                    workgraph_id=wg, task_id=task, source="i",
                    from_status="todo", to_status="doing",
                    timestamp=datetime.now(UTC), agent_id=agent,
                )
            )

        async def hb(wg, task):
            return await repo.store(
                EventFactory.task_heartbeat(
                    workgraph_id=wg, task_id=task, source="i",
                    timestamp=datetime.now(UTC),
                )
            )

        a1 = await sc(wg1, "t1", "ag_1")
        await sc(wg1, "t2", "ag_2")
        await hb(wg1, "t1")
        await sc(wg2, "t3", "ag_1")
        await sc(wg3, "t4", "ag_2")

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            h = {"Authorization": "Bearer t"}
            by_wg = (await c.get(f"/events?workgraph_id={wg1}", headers=h)).json()
            assert len(by_wg["events"]) == 3
            assert by_wg["filter_applied"] == {"workgraph_id": wg1}

            by_agent_ns = (
                await c.get(
                    "/events?agent_id=ag_1&type_namespace=task", headers=h
                )
            ).json()
            # ag_1 task.state_changed only: a1 (wg1/t1) + wg2/t3
            assert len(by_agent_ns["events"]) == 2
            assert all(
                e["event"]["type"] == "task.state_changed"
                for e in by_agent_ns["events"]
            )

            pg = (
                await c.get(
                    f"/events?workgraph_id={wg1}&limit=2", headers=h
                )
            ).json()
            assert len(pg["events"]) == 2
            assert pg["next_from_id"] == a1 + 2
            pg2 = (
                await c.get(
                    f"/events?workgraph_id={wg1}&limit=2"
                    f"&from_id={pg['next_from_id']}",
                    headers=h,
                )
            ).json()
            assert len(pg2["events"]) == 1  # 3 total, page 2 has the last
            assert pg2["next_from_id"] is None
