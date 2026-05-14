import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from vfobs.config import Settings
from vfobs.main import create_app


@pytest.fixture
async def app_under_test(vfobs_database_url):
    settings = Settings(
        database_url=vfobs_database_url,  # type: ignore[arg-type]
        ingest_token=SecretStr("test"),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.mark.integration
async def test_healthz_via_asgi(app_under_test):
    transport = ASGITransport(app=app_under_test)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.integration
async def test_readyz_via_asgi_with_real_postgres(app_under_test):
    transport = ASGITransport(app=app_under_test)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


@pytest.mark.integration
async def test_metrics_via_asgi(app_under_test):
    transport = ASGITransport(app=app_under_test)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as client:
        await client.get("/healthz")  # generate one request to count
        resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    body = resp.text
    assert "vfobs_http_requests_total" in body
    assert "vfobs_http_request_duration_seconds" in body
