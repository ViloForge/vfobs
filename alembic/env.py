from logging.config import fileConfig
from urllib.parse import urlparse

from alembic import context
from sqlalchemy import engine_from_config, pool

from vfobs.config import Settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_sync_url() -> str:
    """Resolve a sync DB URL for alembic from Settings.

    Settings holds the runtime async URL (e.g. postgresql+asyncpg://...).
    Alembic runs synchronously via psycopg (v3); swap to +psycopg.
    """
    settings = Settings()  # type: ignore[call-arg]
    raw = str(settings.database_url)
    parsed = urlparse(raw)
    sync_scheme = "postgresql+psycopg"
    return raw.replace(parsed.scheme, sync_scheme, 1)


def run_migrations_offline() -> None:
    url = _resolve_sync_url()
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolve_sync_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
