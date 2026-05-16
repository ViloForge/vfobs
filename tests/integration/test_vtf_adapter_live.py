"""Integration: VtfClient against a real ASGI round-trip whose
fake vtaskforge is DERIVED FROM THE REAL CONTRACT (kb
feedback-external-contract-grounding): DRF `Token` scheme,
GET /v2/auth/validate/ (200 identity / 401), GET /v2/tasks/<id>/,
GET /v2/milestones/<id>/.
"""

import httpx
import pytest
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from vfobs.adapters.dto import TaskMetadata, VtfPrincipal, WorkgraphMetadata
from vfobs.adapters.vtf import VtfAuthError, VtfClient
from vfobs.config import Settings

BASE = "http://vtf.local"


def _fake_vtaskforge() -> FastAPI:
    """Mirrors real vtaskforge: requires `Authorization: Token <t>`;
    a non-Token / "bad" token → 401 (like DRF IsAuthenticated)."""
    app = FastAPI()
    seen: dict[str, str] = {}

    def _check(authorization: str | None):
        seen["auth"] = authorization or ""
        if not authorization or not authorization.startswith("Token "):
            return False
        return authorization != "Token bad"

    @app.get("/v2/auth/validate/")
    def validate(authorization: str = Header(default="")):
        if not _check(authorization):
            return JSONResponse({"detail": "Invalid token."}, status_code=401)
        return {
            "user_id": 42, "username": "live-op",
            "user_type": "human", "is_staff": False, "projects": [],
        }

    @app.get("/v2/tasks/{tid}/")
    def get_task(tid: str, authorization: str = Header(default="")):
        if not _check(authorization):
            return JSONResponse({"detail": "x"}, status_code=401)
        return {"id": tid, "title": "Live Task", "status": "doing"}

    @app.get("/v2/milestones/{mid}/")
    def get_ms(mid: str, authorization: str = Header(default="")):
        if not _check(authorization):
            return JSONResponse({"detail": "x"}, status_code=401)
        return {"id": mid, "name": "Live MS", "status": "doing"}

    app.state.seen = seen
    return app


def _client(fake) -> VtfClient:
    http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fake), base_url=BASE, timeout=5
    )
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr("x"),
        vtaskforge_url=BASE,  # type: ignore[arg-type]
    )
    return VtfClient(settings, http=http)


@pytest.mark.integration
async def test_adapter_live_round_trip_token_scheme():
    fake = _fake_vtaskforge()
    c = _client(fake)
    p = await c.validate_token("live-tok")
    wg = await c.get_workgraph("wg_1", "live-tok")
    task = await c.get_task("t_1", "live-tok")
    await c.aclose()

    assert p == VtfPrincipal(
        user_id=42, username="live-op", user_type="human", is_staff=False
    )
    assert wg == WorkgraphMetadata(id="wg_1", name="Live MS", status="doing")
    assert task == TaskMetadata(id="t_1", title="Live Task", status="doing")
    # The grounded contract: DRF Token scheme, end-to-end.
    assert fake.state.seen["auth"] == "Token live-tok"


@pytest.mark.integration
async def test_adapter_live_bad_token_denies_not_500():
    c = _client(_fake_vtaskforge())
    with pytest.raises(VtfAuthError):
        await c.validate_token("bad")
    # metadata calls fail-safe to None under a bad token
    assert await c.get_task("t_1", "bad") is None
    await c.aclose()
