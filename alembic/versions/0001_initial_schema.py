"""initial schema — vfobs.events partitioned table + vfobs_app role

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-14
"""
import os
from datetime import date, timedelta

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _month_floor(d: date) -> date:
    return d.replace(day=1)


def _next_month(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1)
    return d.replace(month=d.month + 1, day=1)


def _partition_for_offset(offset: int) -> str:
    today = date.today()
    start = _month_floor(today)
    for _ in range(offset):
        start = _next_month(start)
    end = _next_month(start)
    name = f"events_{start.year}_{start.month:02d}"
    return f"""
        CREATE TABLE vfobs.{name} PARTITION OF vfobs.events
        FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')
    """


def upgrade() -> None:
    app_pw = os.environ.get("VFOBS_APP_DB_PASSWORD", "devpassword")

    op.execute("CREATE SCHEMA IF NOT EXISTS vfobs")

    # Role creation is idempotent — re-running upgrade head is a no-op.
    op.execute(f"""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vfobs_app') THEN
        CREATE ROLE vfobs_app LOGIN PASSWORD '{app_pw}';
      END IF;
    END $$;
    """)

    op.execute("""
    CREATE TABLE vfobs.events (
        id BIGSERIAL NOT NULL,
        v SMALLINT NOT NULL DEFAULT 1,
        workgraph_id TEXT NOT NULL,
        task_id TEXT NULL,
        agent_id TEXT NULL,
        trace_id TEXT NULL,
        source TEXT NOT NULL,
        type TEXT NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        data JSONB NOT NULL DEFAULT '{}'::jsonb,
        classification TEXT NOT NULL DEFAULT 'internal',
        org_id TEXT NOT NULL DEFAULT 'viloforge',
        cluster_id TEXT NOT NULL DEFAULT 'vafi-dev',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT events_type_namespace_chk CHECK (
          type ~ '^(workgraph|task|harness|gate|judge|anomaly)\\.'
        ),
        CONSTRAINT events_classification_chk CHECK (
          classification IN ('public','internal','secret')
        ),
        PRIMARY KEY (id, timestamp)
    ) PARTITION BY RANGE (timestamp)
    """)

    for offset in range(3):
        op.execute(_partition_for_offset(offset))

    op.execute(
        "CREATE INDEX events_workgraph_id_id_idx "
        "ON vfobs.events (workgraph_id, id)"
    )
    op.execute(
        "CREATE INDEX events_task_id_id_idx "
        "ON vfobs.events (task_id, id) WHERE task_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX events_type_id_idx "
        "ON vfobs.events (type, id)"
    )
    op.execute(
        "CREATE INDEX events_timestamp_idx "
        "ON vfobs.events (timestamp)"
    )
    op.execute(
        "CREATE INDEX events_org_cluster_idx "
        "ON vfobs.events (org_id, cluster_id, id)"
    )

    op.execute("GRANT USAGE ON SCHEMA vfobs TO vfobs_app")
    op.execute(
        "GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA vfobs TO vfobs_app"
    )
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA vfobs TO vfobs_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA vfobs "
        "GRANT SELECT, INSERT ON TABLES TO vfobs_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA vfobs "
        "GRANT USAGE, SELECT ON SEQUENCES TO vfobs_app"
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS vfobs CASCADE")
    op.execute("DROP ROLE IF EXISTS vfobs_app")
