from contextlib import asynccontextmanager

from fastapi import FastAPI

from vfobs.adapters.vtf import VtfClient
from vfobs.api import events, health
from vfobs.api.auth import IngestAuth, StaticTokenAuth
from vfobs.api.read_auth import ReadAuth, VtfTokenAuth
from vfobs.config import Settings, get_settings
from vfobs.db import build_engine
from vfobs.middleware.logging import RequestLoggingMiddleware
from vfobs.observability.metrics_registry import metrics_asgi_app
from vfobs.repositories import EventRepository, PostgresEventRepository


@asynccontextmanager
async def _lifespan(app: FastAPI):
    engine = build_engine(app.state.settings)
    app.state.engine = engine
    # Test-mode injectors may pre-populate these; the production path
    # constructs them from the engine + settings here.
    if not hasattr(app.state, "event_repo") or app.state.event_repo is None:
        app.state.event_repo = PostgresEventRepository(engine)
    if not hasattr(app.state, "ingest_auth") or app.state.ingest_auth is None:
        app.state.ingest_auth = StaticTokenAuth(app.state.settings)
    # WG2-T0 read side. Same hasattr/is-None idiom as above (verifier
    # F-adv4). Deviation D-T0-1 (extended): resolution is gated on
    # vtaskforge being configured. A prod deploy WITH the var gets a
    # working read API; a deploy WITHOUT it boots but read endpoints
    # surface a loud 503 (T2+ /readyz asserts read_auth is wired).
    # This keeps the WG1 write-only suite — which runs this lifespan
    # via `with TestClient` and cannot inject vtf_client (frozen
    # fixture, predates T0) — green, instead of failing app startup.
    # VtfClient.__init__ still raises on explicit/misconfigured
    # construction, so the fail-fast intent survives where it can.
    if app.state.settings.vtaskforge_url is not None:
        if not hasattr(app.state, "vtf_client") or app.state.vtf_client is None:
            app.state.vtf_client = VtfClient(app.state.settings)
        if not hasattr(app.state, "read_auth") or app.state.read_auth is None:
            app.state.read_auth = VtfTokenAuth(app.state.vtf_client)
    try:
        yield
    finally:
        if getattr(app.state, "vtf_client", None) is not None:
            await app.state.vtf_client.aclose()
        await engine.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    event_repo: EventRepository | None = None,
    ingest_auth: IngestAuth | None = None,
    read_auth: ReadAuth | None = None,
    vtf_client: VtfClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="vfobs", version="0.0.1", lifespan=_lifespan)
    app.state.settings = settings
    app.state.event_repo = event_repo  # may be None — lifespan resolves
    app.state.ingest_auth = ingest_auth  # may be None — lifespan resolves
    app.state.read_auth = read_auth  # may be None — lifespan resolves
    app.state.vtf_client = vtf_client  # may be None — lifespan resolves
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(health.router)
    app.include_router(events.router)
    app.mount("/metrics", metrics_asgi_app())
    return app
