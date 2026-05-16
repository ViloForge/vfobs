import itertools
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from vfobs.events._dispatch import EVENT_TYPE_REGISTRY
from vfobs.events.base import Event

_MAX_LIMIT = 1000

_INSERT_EVENT = sa.text("""
    INSERT INTO vfobs.events (
        v, workgraph_id, task_id, agent_id, trace_id,
        source, type, timestamp, data, classification,
        org_id, cluster_id
    ) VALUES (
        :v, :workgraph_id, :task_id, :agent_id, :trace_id,
        :source, :type, :timestamp,
        CAST(:data AS JSONB),
        :classification, :org_id, :cluster_id
    ) RETURNING id
""")

_SELECT_BY_ID = sa.text("""
    SELECT id, v, workgraph_id, task_id, agent_id, trace_id,
           source, type, timestamp, data, classification,
           org_id, cluster_id, created_at
    FROM vfobs.events
    WHERE id = :id
""")

_SELECT_COLS = """
    SELECT id, v, workgraph_id, task_id, agent_id, trace_id,
           source, type, timestamp, data, classification,
           org_id, cluster_id, created_at
    FROM vfobs.events
"""


class StoredEvent(BaseModel):
    """Read model (verifier F1, mechanism R2): a persisted event plus
    its DB-assigned id. Keeps the storage id off the write/ingest
    `Event` model — Event's locked v1 schema is untouched. find_*
    return these; read endpoints serialize {id, event}. get_by_id
    intentionally keeps returning a bare Event (D-T1-1)."""

    model_config = ConfigDict(frozen=True)

    id: int
    event: Event


class CostSummary(BaseModel):
    """Aggregate cost rollup (plan §D3). Frozen — every field declared
    (R13). Per verifier F2 the underlying aggregation counts the
    LATEST execution_summary per task, so task_count == the number of
    contributing tasks and (post-dedup) == sample_event_count."""

    model_config = ConfigDict(frozen=True)

    total_cost_usd: float
    total_tokens: int
    total_turns: int
    task_count: int
    sample_event_count: int


def _event_to_row(event: Event) -> dict[str, Any]:
    dump = event.model_dump(mode="json")
    return {
        "v": dump["v"],
        "workgraph_id": dump["workgraph_id"],
        "task_id": dump.get("task_id"),
        "agent_id": dump.get("agent_id"),
        "trace_id": dump.get("trace_id"),
        "source": dump["source"],
        "type": dump["type"],
        "timestamp": event.timestamp,
        "data": json.dumps(dump["data"]),
        "classification": dump["classification"],
        "org_id": dump["org_id"],
        "cluster_id": dump["cluster_id"],
    }


def _row_to_event(row: Mapping) -> Event:
    # Deviation D-T1-1: intentionally id-free so get_by_id behavior +
    # its whole-object-equality test stay unchanged. find_* attach the
    # id explicitly via model_copy after building the event.
    event_cls = EVENT_TYPE_REGISTRY[row["type"]]
    raw_data = row["data"]
    data = raw_data if isinstance(raw_data, dict) else json.loads(raw_data)
    payload = {
        "v": row["v"],
        "type": row["type"],
        "workgraph_id": row["workgraph_id"],
        "task_id": row["task_id"],
        "agent_id": row["agent_id"],
        "trace_id": row["trace_id"],
        "source": row["source"],
        "timestamp": row["timestamp"],
        "classification": row["classification"],
        "org_id": row["org_id"],
        "cluster_id": row["cluster_id"],
        "data": data,
    }
    return event_cls.model_validate(payload)


def _row_to_stored(row: Mapping) -> "StoredEvent":
    """find_* read path (verifier F1, mechanism R2): wrap the
    reconstructed event with its DB id in the StoredEvent read model.
    Event itself is unchanged — the ingest schema stays locked."""
    return StoredEvent(id=row["id"], event=_row_to_event(row))


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, _MAX_LIMIT))


class EventRepository(ABC):
    """Async storage abstraction for vfobs events. v1 has two impls:
    PostgresEventRepository (production) and InMemoryEventRepository
    (test double; real LSP substitute, not a mock)."""

    @abstractmethod
    async def store(self, event: Event) -> int:
        """Persist event, return the assigned id."""

    @abstractmethod
    async def get_by_id(self, event_id: int) -> Event | None:
        """Retrieve a single event by id (testing/debugging)."""

    @abstractmethod
    async def find_by_workgraph(
        self, workgraph_id: str, *, from_id: int | None = None, limit: int = 100
    ) -> list[StoredEvent]:
        """Events for a workgraph, id ASC, id-inclusive from_id cursor."""

    @abstractmethod
    async def find_by_task(
        self, task_id: str, *, from_id: int | None = None, limit: int = 100
    ) -> list[StoredEvent]:
        """Events for a task, id ASC, id-inclusive from_id cursor."""

    @abstractmethod
    async def find_filtered(
        self,
        *,
        workgraph_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        type_: str | None = None,
        type_namespace: str | None = None,
        org_id: str | None = None,
        from_id: int | None = None,
        limit: int = 100,
    ) -> list[StoredEvent]:
        """AND-combined filtered query, id ASC, id-inclusive cursor."""

    @abstractmethod
    async def cost_summary(
        self, *, workgraph_id: str | None = None, agent_id: str | None = None
    ) -> CostSummary:
        """Cost rollup. Exactly one of workgraph_id|agent_id (else
        ValueError). Counts the latest execution_summary per task
        (verifier F2 — no rework double-count)."""


class PostgresEventRepository(EventRepository):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def store(self, event: Event) -> int:
        row = _event_to_row(event)
        async with self._engine.begin() as conn:
            result = await conn.execute(_INSERT_EVENT, row)
            return int(result.scalar_one())

    async def get_by_id(self, event_id: int) -> Event | None:
        async with self._engine.connect() as conn:
            result = await conn.execute(_SELECT_BY_ID, {"id": event_id})
            row = result.mappings().one_or_none()
        return _row_to_event(row) if row else None

    async def _fetch(
        self, where: str, params: dict[str, Any]
    ) -> list[StoredEvent]:
        stmt = sa.text(
            f"{_SELECT_COLS} WHERE {where} ORDER BY id ASC LIMIT :limit"
        )
        async with self._engine.connect() as conn:
            result = await conn.execute(stmt, params)
            rows = result.mappings().all()
        return [_row_to_stored(r) for r in rows]

    @staticmethod
    def _cursor(clauses: list[str], params: dict[str, Any], from_id: int | None) -> None:
        # Build the from_id clause in Python — asyncpg can't infer the
        # type of a NULL bigint param in a `:p IS NULL OR ...` idiom.
        if from_id is not None:
            clauses.append("id >= :from_id")
            params["from_id"] = from_id

    async def find_by_workgraph(
        self, workgraph_id: str, *, from_id: int | None = None, limit: int = 100
    ) -> list[StoredEvent]:
        clauses = ["workgraph_id = :workgraph_id"]
        params: dict[str, Any] = {
            "workgraph_id": workgraph_id,
            "limit": _clamp_limit(limit),
        }
        self._cursor(clauses, params, from_id)
        return await self._fetch(" AND ".join(clauses), params)

    async def find_by_task(
        self, task_id: str, *, from_id: int | None = None, limit: int = 100
    ) -> list[StoredEvent]:
        clauses = ["task_id = :task_id"]
        params: dict[str, Any] = {
            "task_id": task_id,
            "limit": _clamp_limit(limit),
        }
        self._cursor(clauses, params, from_id)
        return await self._fetch(" AND ".join(clauses), params)

    async def find_filtered(
        self,
        *,
        workgraph_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        type_: str | None = None,
        type_namespace: str | None = None,
        org_id: str | None = None,
        from_id: int | None = None,
        limit: int = 100,
    ) -> list[StoredEvent]:
        # AC-T1-5 precedence is documentation order; all AND-combined.
        clauses: list[str] = ["1 = 1"]
        params: dict[str, Any] = {"limit": _clamp_limit(limit)}
        if workgraph_id is not None:
            clauses.append("workgraph_id = :workgraph_id")
            params["workgraph_id"] = workgraph_id
        if task_id is not None:
            clauses.append("task_id = :task_id")
            params["task_id"] = task_id
        if agent_id is not None:
            clauses.append("agent_id = :agent_id")
            params["agent_id"] = agent_id
        if org_id is not None:
            clauses.append("org_id = :org_id")
            params["org_id"] = org_id
        if type_ is not None:
            clauses.append("type = :type_")
            params["type_"] = type_
        if type_namespace is not None:
            clauses.append("split_part(type, '.', 1) = :type_namespace")
            params["type_namespace"] = type_namespace
        self._cursor(clauses, params, from_id)
        return await self._fetch(" AND ".join(clauses), params)

    async def cost_summary(
        self, *, workgraph_id: str | None = None, agent_id: str | None = None
    ) -> CostSummary:
        if (workgraph_id is None) == (agent_id is None):
            raise ValueError(
                "cost_summary requires exactly one of workgraph_id or agent_id"
            )
        if workgraph_id is not None:
            scope, params = "workgraph_id = :scope", {"scope": workgraph_id}
        else:
            scope, params = "agent_id = :scope", {"scope": agent_id}
        # verifier F2: DISTINCT ON keeps the latest summary-bearing
        # state_changed per task; the outer query then aggregates.
        stmt = sa.text(f"""
            WITH latest AS (
                SELECT DISTINCT ON (task_id)
                       task_id,
                       data->'execution_summary' AS es
                FROM vfobs.events
                WHERE type = 'task.state_changed'
                  AND task_id IS NOT NULL
                  AND data ? 'execution_summary'
                  AND data->'execution_summary' IS NOT NULL
                  AND data->'execution_summary' != 'null'::jsonb
                  AND {scope}
                ORDER BY task_id, id DESC
            )
            SELECT
              COALESCE(SUM((es->>'cost_usd')::numeric), 0)::float
                  AS total_cost_usd,
              COALESCE(SUM((es->>'total_tokens')::int), 0) AS total_tokens,
              COALESCE(SUM((es->>'num_turns')::int), 0) AS total_turns,
              COUNT(*) AS task_count,
              COUNT(*) AS sample_event_count
            FROM latest
        """)
        async with self._engine.connect() as conn:
            result = await conn.execute(stmt, params)
            row = result.mappings().one()
        return CostSummary(
            total_cost_usd=float(row["total_cost_usd"]),
            total_tokens=int(row["total_tokens"]),
            total_turns=int(row["total_turns"]),
            task_count=int(row["task_count"]),
            sample_event_count=int(row["sample_event_count"]),
        )


class InMemoryEventRepository(EventRepository):
    def __init__(self) -> None:
        self._events: dict[int, Event] = {}
        self._next_id = itertools.count(1)

    async def store(self, event: Event) -> int:
        eid = next(self._next_id)
        self._events[eid] = event
        return eid

    async def get_by_id(self, event_id: int) -> Event | None:
        return self._events.get(event_id)

    def _scan(
        self, predicate, *, from_id: int | None, limit: int
    ) -> list[StoredEvent]:
        out: list[StoredEvent] = []
        cap = _clamp_limit(limit)
        for eid, ev in sorted(self._events.items()):
            if from_id is not None and eid < from_id:
                continue
            if not predicate(ev):
                continue
            out.append(StoredEvent(id=eid, event=ev))  # F1/R2 read model
            if len(out) >= cap:
                break
        return out

    async def find_by_workgraph(
        self, workgraph_id: str, *, from_id: int | None = None, limit: int = 100
    ) -> list[StoredEvent]:
        return self._scan(
            lambda ev: ev.workgraph_id == workgraph_id,
            from_id=from_id,
            limit=limit,
        )

    async def find_by_task(
        self, task_id: str, *, from_id: int | None = None, limit: int = 100
    ) -> list[StoredEvent]:
        return self._scan(
            lambda ev: ev.task_id == task_id, from_id=from_id, limit=limit
        )

    async def find_filtered(
        self,
        *,
        workgraph_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        type_: str | None = None,
        type_namespace: str | None = None,
        org_id: str | None = None,
        from_id: int | None = None,
        limit: int = 100,
    ) -> list[StoredEvent]:
        def pred(ev: Event) -> bool:
            if workgraph_id is not None and ev.workgraph_id != workgraph_id:
                return False
            if task_id is not None and ev.task_id != task_id:
                return False
            if agent_id is not None and ev.agent_id != agent_id:
                return False
            if org_id is not None and ev.org_id != org_id:
                return False
            if type_ is not None and ev.type != type_:
                return False
            if (
                type_namespace is not None
                and ev.type.split(".", 1)[0] != type_namespace
            ):
                return False
            return True

        return self._scan(pred, from_id=from_id, limit=limit)

    async def cost_summary(
        self, *, workgraph_id: str | None = None, agent_id: str | None = None
    ) -> CostSummary:
        if (workgraph_id is None) == (agent_id is None):
            raise ValueError(
                "cost_summary requires exactly one of workgraph_id or agent_id"
            )
        # verifier F2: keep the highest-id summary-bearing
        # task.state_changed per task_id, then reduce.
        latest: dict[str, tuple[int, Any]] = {}
        for eid, ev in self._events.items():
            if ev.type != "task.state_changed" or ev.task_id is None:
                continue
            if workgraph_id is not None and ev.workgraph_id != workgraph_id:
                continue
            if agent_id is not None and ev.agent_id != agent_id:
                continue
            es = getattr(ev.data, "execution_summary", None)
            if es is None:
                continue
            cur = latest.get(ev.task_id)
            if cur is None or eid > cur[0]:
                latest[ev.task_id] = (eid, es)
        total_cost = 0.0
        total_tokens = 0
        total_turns = 0
        for _eid, es in latest.values():
            if es.cost_usd is not None:
                total_cost += es.cost_usd
            if es.total_tokens is not None:
                total_tokens += es.total_tokens
            if es.num_turns is not None:
                total_turns += es.num_turns
        return CostSummary(
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            total_turns=total_turns,
            task_count=len(latest),
            sample_event_count=len(latest),
        )
