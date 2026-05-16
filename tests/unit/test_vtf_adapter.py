"""VtfClient unit tests — against the REAL grounded vtaskforge
contract (kb feedback-external-contract-grounding):
GET /v2/auth/validate/ with `Authorization: Token <t>`,
GET /v2/tasks/<id>/, GET /v2/milestones/<id>/ (== workgraph).
"""

import httpx
import pytest
import respx
from pydantic import SecretStr

from vfobs.adapters.dto import TaskMetadata, VtfPrincipal, WorkgraphMetadata
from vfobs.adapters.vtf import VtfAuthError, VtfClient
from vfobs.config import Settings

BASE = "http://vtf.test"


def _settings(url=BASE):
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr("x"),
        vtaskforge_url=url,  # type: ignore[arg-type]
    )


@pytest.mark.unit
def test_requires_url():
    with pytest.raises(ValueError, match="VFOBS_VTASKFORGE_URL"):
        VtfClient(_settings(url=None))


@pytest.mark.unit
@respx.mock
async def test_validate_token_200_uses_token_scheme_and_real_fields():
    route = respx.get(f"{BASE}/v2/auth/validate/").mock(
        return_value=httpx.Response(
            200,
            json={
                "user_id": 7, "username": "op", "user_type": "human",
                "is_staff": True, "projects": [],
            },
        )
    )
    c = VtfClient(_settings())
    p = await c.validate_token("tok-abc")
    await c.aclose()
    assert p == VtfPrincipal(
        user_id=7, username="op", user_type="human", is_staff=True
    )
    # DRF Token scheme, NOT Bearer (the grounded contract)
    assert route.calls.last.request.headers["Authorization"] == "Token tok-abc"


@pytest.mark.unit
@respx.mock
async def test_validate_token_401_raises_auth_error():
    respx.get(f"{BASE}/v2/auth/validate/").mock(
        return_value=httpx.Response(401)
    )
    c = VtfClient(_settings())
    with pytest.raises(VtfAuthError):
        await c.validate_token("bad")
    await c.aclose()


@pytest.mark.unit
@respx.mock
async def test_validate_token_non_json_200_denies_not_500():
    # the exact prod failure: SPA HTML on a 200 → must DENY, not raise
    respx.get(f"{BASE}/v2/auth/validate/").mock(
        return_value=httpx.Response(200, text="<!doctype html>")
    )
    c = VtfClient(_settings())
    with pytest.raises(VtfAuthError):
        await c.validate_token("tok")
    await c.aclose()


@pytest.mark.unit
@respx.mock
async def test_validate_token_network_error_denies():
    respx.get(f"{BASE}/v2/auth/validate/").mock(
        side_effect=httpx.ConnectError("refused")
    )
    c = VtfClient(_settings())
    with pytest.raises(VtfAuthError):
        await c.validate_token("tok")
    await c.aclose()


@pytest.mark.unit
@respx.mock
async def test_get_task_200_and_failsafe():
    respx.get(f"{BASE}/v2/tasks/t_1/").mock(
        return_value=httpx.Response(
            200, json={"id": "t_1", "title": "T", "status": "doing"}
        )
    )
    respx.get(f"{BASE}/v2/tasks/nope/").mock(
        return_value=httpx.Response(200, text="<!doctype html>")
    )
    respx.get(f"{BASE}/v2/tasks/err/").mock(
        return_value=httpx.Response(500)
    )
    c = VtfClient(_settings())
    assert await c.get_task("t_1", "tok") == TaskMetadata(
        id="t_1", title="T", status="doing"
    )
    assert await c.get_task("nope", "tok") is None   # non-JSON → None
    assert await c.get_task("err", "tok") is None     # 500 → None
    await c.aclose()


@pytest.mark.unit
@respx.mock
async def test_get_workgraph_hits_milestones_endpoint_failsafe():
    respx.get(f"{BASE}/v2/milestones/wg_1/").mock(
        return_value=httpx.Response(
            200, json={"id": "wg_1", "name": "M1", "status": "doing"}
        )
    )
    c = VtfClient(_settings())
    wg = await c.get_workgraph("wg_1", "tok")
    await c.aclose()
    assert wg == WorkgraphMetadata(id="wg_1", name="M1", status="doing")
