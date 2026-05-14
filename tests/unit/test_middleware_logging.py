import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from vfobs.middleware.logging import RequestLoggingMiddleware
from vfobs.observability.metrics_registry import REQUESTS


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    def ping():
        return PlainTextResponse("pong")

    return app


@pytest.mark.unit
def test_middleware_increments_counter_and_logs(caplog):
    caplog.set_level(logging.INFO, logger="vfobs.request")
    client = TestClient(_app())
    before = REQUESTS.labels(method="GET", path="/ping", status=200)._value.get()  # type: ignore[attr-defined]
    resp = client.get("/ping")
    assert resp.status_code == 200
    after = REQUESTS.labels(method="GET", path="/ping", status=200)._value.get()  # type: ignore[attr-defined]
    assert after == before + 1

    # one log record from our middleware
    records = [r for r in caplog.records if r.name == "vfobs.request"]
    assert len(records) >= 1
    rec = records[-1]
    assert rec.method == "GET"  # type: ignore[attr-defined]
    assert rec.path == "/ping"  # type: ignore[attr-defined]
    assert rec.status == 200  # type: ignore[attr-defined]
    assert isinstance(rec.duration_ms, int)  # type: ignore[attr-defined]
    assert rec.request_id != "-"  # type: ignore[attr-defined]
