from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from vfobs.api.health import healthz, readyz
from vfobs.config import Settings


def _settings():
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr("test"),
    )


@pytest.mark.unit
async def test_healthz_returns_ok_without_db():
    resp = await healthz()
    assert resp == {"status": "ok"}


@pytest.mark.unit
async def test_readyz_returns_ok_on_db_success():
    app = FastAPI()
    engine = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None
    engine.connect = MagicMock(return_value=cm)
    app.state.engine = engine

    class _Req:
        def __init__(self, app):
            self.app = app

    resp = await readyz(_Req(app))  # type: ignore[arg-type]
    assert resp.status_code == 200
    assert b'"status":"ok"' in resp.body
    assert b'"db":"ok"' in resp.body


@pytest.mark.unit
async def test_readyz_returns_503_on_db_failure():
    app = FastAPI()
    engine = MagicMock()

    cm = AsyncMock()
    async def _aenter(*_):
        raise ConnectionError("boom")
    cm.__aenter__ = _aenter
    cm.__aexit__ = AsyncMock(return_value=None)
    engine.connect = MagicMock(return_value=cm)
    app.state.engine = engine

    class _Req:
        def __init__(self, app):
            self.app = app

    resp = await readyz(_Req(app))  # type: ignore[arg-type]
    assert resp.status_code == 503
    assert b"ConnectionError" in resp.body
    assert b"not_ready" in resp.body
