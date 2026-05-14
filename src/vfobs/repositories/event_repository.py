import itertools
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from vfobs.events._dispatch import EVENT_TYPE_REGISTRY
from vfobs.events.base import Event

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
