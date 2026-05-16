import httpx
import pytest
import respx
from pydantic import SecretStr

from vfobs.adapters.dto import TaskMetadata, WhoamiPrincipal, WorkgraphMetadata
from vfobs.adapters.vtf import VtfAuthError, VtfClient
from vfobs.config import Settings

BASE = "http://vtf.test"


def _settings(url: str | None = BASE) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr("x"),
        vtaskforge_url=url,  # type: ignore[arg-type]
    )


@pytest.mark.unit
def test_vtfclient_requires_url() -> None:
    # Deviation D-T0-1: the prod "must be set" guarantee lives here.
    with pytest.raises(ValueError, match="VFOBS_VTASKFORGE_URL"):
        VtfClient(_settings(url=None))


@pytest.mark.unit
@respx.mock
async def test_whoami_200_returns_principal() -> None:
    route = respx.get(f"{BASE}/v2/auth/whoami").mock(
        return_value=httpx.Response(
            200, json={"user_id": "op-1", "display_name": "Op One"}
        )
    )
    client = VtfClient(_settings())
    who = await client.whoami("tok-abc")
    await client.aclose()

    assert who == WhoamiPrincipal(user_id="op-1", display_name="Op One")
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-abc"


@pytest.mark.unit
@respx.mock
async def test_whoami_401_raises_vtf_auth_error() -> None:
    respx.get(f"{BASE}/v2/auth/whoami").mock(return_value=httpx.Response(401))
    client = VtfClient(_settings())
    with pytest.raises(VtfAuthError):
        await client.whoami("bad")
    await client.aclose()


@pytest.mark.unit
@respx.mock
async def test_get_workgraph_200_projects_metadata() -> None:
    respx.get(f"{BASE}/v2/workgraphs/wg_1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "wg_1",
                "status": "doing",
                "kind": "infrastructure",
                "target_repos": ["viloforge/vfobs"],
                "tags": ["t"],
                "created_at": "2026-05-16T00:00:00Z",
                "extra_field_we_ignore": 999,
            },
        )
    )
    client = VtfClient(_settings())
    wg = await client.get_workgraph("wg_1", "tok")
    await client.aclose()

    assert wg == WorkgraphMetadata(
        id="wg_1",
        status="doing",
        kind="infrastructure",
        target_repos=["viloforge/vfobs"],
        tags=["t"],
        created_at="2026-05-16T00:00:00Z",
    )


@pytest.mark.unit
@respx.mock
async def test_get_workgraph_404_returns_none() -> None:
    respx.get(f"{BASE}/v2/workgraphs/missing/").mock(
        return_value=httpx.Response(404)
    )
    client = VtfClient(_settings())
    assert await client.get_workgraph("missing", "tok") is None
    await client.aclose()


@pytest.mark.unit
@respx.mock
async def test_get_task_200_and_404() -> None:
    respx.get(f"{BASE}/v2/tasks/t_1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "t_1",
                "workgraph_id": "wg_1",
                "status": "doing",
                "title": "A task",
            },
        )
    )
    respx.get(f"{BASE}/v2/tasks/none/").mock(return_value=httpx.Response(404))
    client = VtfClient(_settings())
    task = await client.get_task("t_1", "tok")
    missing = await client.get_task("none", "tok")
    await client.aclose()

    assert task == TaskMetadata(
        id="t_1", workgraph_id="wg_1", status="doing", title="A task"
    )
    assert missing is None
