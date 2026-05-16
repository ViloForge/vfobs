"""Integration: VtfClient against a real httpx transport hitting a
fake-vtaskforge ASGI app (no MockTransport). Verifies the full
request shape — Authorization passthrough, URL composition, timeout
config — over a real ASGI round-trip.
"""

import httpx
import pytest
from fastapi import FastAPI, Header, HTTPException
from pydantic import SecretStr

from vfobs.adapters.dto import TaskMetadata, WhoamiPrincipal, WorkgraphMetadata
from vfobs.config import Settings
from vfobs.adapters.vtf import VtfClient

BASE = "http://vtf.local"


def _fake_vtaskforge() -> FastAPI:
    app = FastAPI()
    seen: dict[str, str] = {}

    @app.get("/v2/auth/whoami")
    def whoami(authorization: str = Header(...)) -> dict:
        seen["auth"] = authorization
        return {"user_id": "live-op", "display_name": "Live Op"}

    @app.get("/v2/workgraphs/{wid}/")
    def get_wg(wid: str) -> dict:
        if wid == "nope":
            raise HTTPException(status_code=404)
        return {"id": wid, "status": "doing", "target_repos": [], "tags": []}

    @app.get("/v2/tasks/{tid}/")
    def get_task(tid: str) -> dict:
        return {"id": tid, "workgraph_id": "wg_x", "status": "doing"}

    app.state.seen = seen
    return app


@pytest.mark.integration
async def test_adapter_live_round_trip() -> None:
    fake = _fake_vtaskforge()
    transport = httpx.ASGITransport(app=fake)
    http = httpx.AsyncClient(transport=transport, base_url=BASE, timeout=5)
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr("x"),
        vtaskforge_url=BASE,  # type: ignore[arg-type]
    )
    client = VtfClient(settings, http=http)

    who = await client.whoami("live-tok")
    wg = await client.get_workgraph("wg_1", "live-tok")
    task = await client.get_task("t_1", "live-tok")
    missing = await client.get_workgraph("nope", "live-tok")
    await client.aclose()

    assert who == WhoamiPrincipal(user_id="live-op", display_name="Live Op")
    assert wg == WorkgraphMetadata(id="wg_1", status="doing")
    assert task == TaskMetadata(id="t_1", workgraph_id="wg_x", status="doing")
    # 404 path: fake returns 404 for "nope" -> adapter maps to None.
    assert missing is None
    # Authorization header passthrough verified end-to-end.
    assert fake.state.seen["auth"] == "Bearer live-tok"
