import os
from collections.abc import Iterator

import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer("postgres:15-alpine")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture
def pg_url(pg_container: PostgresContainer) -> str:
    """Sync DB URL using psycopg (v3) — for direct test inspection queries."""
    raw = pg_container.get_connection_url()
    return raw.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)


@pytest.fixture
def vfobs_database_url(pg_url: str) -> Iterator[str]:
    """Sets VFOBS_DATABASE_URL env var as the async-driver form for the test
    container, restoring any prior value on teardown."""
    async_url = pg_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    prior = os.environ.get("VFOBS_DATABASE_URL")
    os.environ["VFOBS_DATABASE_URL"] = async_url
    try:
        yield async_url
    finally:
        if prior is None:
            os.environ.pop("VFOBS_DATABASE_URL", None)
        else:
            os.environ["VFOBS_DATABASE_URL"] = prior
