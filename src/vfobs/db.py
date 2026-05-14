from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from vfobs.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(str(settings.database_url), echo=False, future=True)
