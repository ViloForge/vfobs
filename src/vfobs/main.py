from contextlib import asynccontextmanager

from fastapi import FastAPI

from vfobs.api import health
from vfobs.config import Settings, get_settings
from vfobs.db import build_engine
from vfobs.middleware.logging import RequestLoggingMiddleware
from vfobs.observability.metrics_registry import metrics_asgi_app


@asynccontextmanager
async def _lifespan(app: FastAPI):
    engine = build_engine(app.state.settings)
    app.state.engine = engine
    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="vfobs", version="0.0.1", lifespan=_lifespan)
    app.state.settings = settings
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(health.router)
    app.mount("/metrics", metrics_asgi_app())
    return app
