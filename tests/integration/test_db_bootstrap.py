import subprocess
from pathlib import Path

import pytest
import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_INDEXES = [
    "events_workgraph_id_id_idx",
    "events_task_id_id_idx",
    "events_type_id_idx",
    "events_timestamp_idx",
    "events_org_cluster_idx",
]


def _run_alembic_upgrade(database_url: str) -> subprocess.CompletedProcess:
    env = {
        "VFOBS_DATABASE_URL": database_url,
        "VFOBS_INGEST_TOKEN": "test",
        "VFOBS_APP_DB_PASSWORD": "testapppw",
        "PATH": "/usr/bin:/bin:" + str(REPO_ROOT / ".venv" / "bin"),
    }
    return subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "alembic"), "upgrade", "head"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _sync_engine(pg_url: str) -> sa.Engine:
    # tests use the sync psycopg2 URL the container hands us
    return sa.create_engine(pg_url)


@pytest.mark.integration
def test_bootstrap_creates_schema_table_role(pg_url, vfobs_database_url):
    _run_alembic_upgrade(vfobs_database_url)
    engine = _sync_engine(pg_url)
    with engine.connect() as conn:
        schemas = {
            row[0]
            for row in conn.execute(
                sa.text("SELECT schema_name FROM information_schema.schemata")
            )
        }
        assert "vfobs" in schemas

        tables = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'vfobs'"
                )
            )
        }
        assert "events" in tables

        roles = {
            row[0]
            for row in conn.execute(sa.text("SELECT rolname FROM pg_roles"))
        }
        assert "vfobs_app" in roles

        indexes = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'vfobs'"
                )
            )
        }
        for ix in EXPECTED_INDEXES:
            assert ix in indexes, f"missing index {ix}"


@pytest.mark.integration
def test_bootstrap_is_idempotent(pg_url, vfobs_database_url):
    _run_alembic_upgrade(vfobs_database_url)
    # second run must not raise
    _run_alembic_upgrade(vfobs_database_url)

    engine = _sync_engine(pg_url)
    with engine.connect() as conn:
        count = conn.execute(
            sa.text("SELECT count(*) FROM alembic_version")
        ).scalar_one()
        assert count == 1


@pytest.mark.integration
def test_vfobs_app_grants_are_minimal(pg_url, vfobs_database_url):
    _run_alembic_upgrade(vfobs_database_url)
    engine = _sync_engine(pg_url)
    with engine.connect() as conn:
        privs = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'vfobs_app' AND table_schema = 'vfobs'"
                )
            )
        }
        assert privs == {"SELECT", "INSERT"}, f"unexpected privs: {privs}"


@pytest.mark.integration
def test_events_table_is_time_partitioned(pg_url, vfobs_database_url):
    _run_alembic_upgrade(vfobs_database_url)
    engine = _sync_engine(pg_url)
    with engine.connect() as conn:
        # parent relkind 'p' = partitioned table
        kind = conn.execute(
            sa.text(
                "SELECT relkind FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'vfobs' AND c.relname = 'events'"
            )
        ).scalar_one()
        assert kind == "p"

        # at least one child partition
        children = conn.execute(
            sa.text(
                "SELECT count(*) FROM pg_inherits i "
                "JOIN pg_class c ON c.oid = i.inhparent "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'vfobs' AND c.relname = 'events'"
            )
        ).scalar_one()
        assert children >= 1
