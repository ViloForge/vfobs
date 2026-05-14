from contextlib import asynccontextmanager

from fastapi import FastAPI

from vfobs.api import events, health
from vfobs.api.auth import IngestAuth, StaticTokenAuth
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
    try:
        yield
    finally:
        await engine.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    event_repo: EventRepository | None = None,
    ingest_auth: IngestAuth | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="vfobs", version="0.0.1", lifespan=_lifespan)
    app.state.settings = settings
    app.state.event_repo = event_repo  # may be None — lifespan resolves
    app.state.ingest_auth = ingest_auth  # may be None — lifespan resolves
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(health.router)
    app.include_router(events.router)
    app.mount("/metrics", metrics_asgi_app())
    return app
