"""Integration: WG2-T4 cost endpoints against real Postgres —
2 workgraphs + 2 agents incl. a reworked task; asserts the
DISTINCT-ON (verifier F2) math matches expectation. WG1 single-loop
pattern; uuid-isolated.
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
from vfobs.events.namespaces.task import ExecutionSummary
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
async def test_cost_live(vfobs_database_url):
    _alembic(vfobs_database_url)
    ns = uuid.uuid4().hex[:8]
    wg = f"wg_{ns}"
    ag = f"ag_{ns}"
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

        async def sc(task, agent, es):
            return await repo.store(
                EventFactory.task_state_changed(
                    workgraph_id=wg, task_id=task, source="i",
                    from_status="doing", to_status="done",
                    execution_summary=es, agent_id=agent,
                    timestamp=datetime.now(UTC),
                )
            )

        await sc("t1", ag, ExecutionSummary(
            num_turns=2, total_tokens=100, cost_usd=0.50))
        # reworked task: two summary-bearing events; latest wins (F2)
        await sc("t_rw", ag, ExecutionSummary(
            num_turns=1, total_tokens=10, cost_usd=0.10))
        await sc("t_rw", ag, ExecutionSummary(
            num_turns=5, total_tokens=90, cost_usd=0.40))
        # different agent, same workgraph
        await sc("t3", "other", ExecutionSummary(cost_usd=9.0))

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            h = {"Authorization": "Bearer t"}
            w = (await c.get(f"/workgraphs/{wg}/cost", headers=h)).json()
            a = (await c.get(f"/agents/{ag}/cost", headers=h)).json()
            miss = await c.get(f"/workgraphs/ghost_{ns}/cost", headers=h)

    # workgraph: t1 (0.50) + t_rw latest (0.40) + t3 (9.0) = 9.90
    assert w["summary"]["total_cost_usd"] == pytest.approx(9.90)
    assert w["summary"]["task_count"] == 3  # t1, t_rw (once), t3
    # agent ag: t1 (0.50) + t_rw latest (0.40) = 0.90, t_rw once
    assert a["summary"]["total_cost_usd"] == pytest.approx(0.90)
    assert a["summary"]["task_count"] == 2
    assert a["summary"]["total_tokens"] == 190  # 100 + 90 (latest)
    assert miss.status_code == 404
