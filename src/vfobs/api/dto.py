"""Read-API response DTOs (frozen, versioned). Event-list items are
the `repositories.StoredEvent` read model serialized directly
(verifier F1 mechanism R2 — the DB id rides the read model, never
the locked ingest `Event` schema)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from vfobs.adapters.dto import TaskMetadata, WorkgraphMetadata
from vfobs.repositories import StoredEvent


class VtfWorkgraphPart(BaseModel):
    # Grounded to the real milestone projection (vfobs "workgraph"
    # == vtaskforge milestone). Fields per MilestoneV2Serializer.
    model_config = ConfigDict(frozen=True)

    status: str | None = None
    name: str | None = None
    description: str | None = None
    order: int | None = None

    @classmethod
    def from_metadata(cls, m: WorkgraphMetadata) -> "VtfWorkgraphPart":
        return cls(
            status=m.status,
            name=m.name,
            description=m.description,
            order=m.order,
        )


class VtfTaskPart(BaseModel):
    # Grounded to the real TaskV2Serializer projection.
    model_config = ConfigDict(frozen=True)

    status: str | None = None
    title: str | None = None
    description: str | None = None

    @classmethod
    def from_metadata(cls, m: TaskMetadata) -> "VtfTaskPart":
        return cls(
            status=m.status,
            title=m.title,
            description=m.description,
        )


class VfobsPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_count: int
    last_event_id: int | None = None
    last_event_type: str | None = None
    last_event_at: datetime | None = None

    @classmethod
    def build(cls, count: int, tail: StoredEvent | None) -> "VfobsPart":
        if tail is None:
            return cls(event_count=count)
        return cls(
            event_count=count,
            last_event_id=tail.id,
            last_event_type=tail.event.type,
            last_event_at=tail.event.timestamp,
        )


class WorkgraphReadResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    v: int = 1
    workgraph_id: str
    vtf: VtfWorkgraphPart | None = None
    vfobs: VfobsPart


class TaskReadResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    v: int = 1
    task_id: str
    vtf: VtfTaskPart | None = None
    vfobs: VfobsPart


class TaskEventsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    v: int = 1
    task_id: str
    events: list[StoredEvent]
    next_from_id: int | None = None


class EventsFilterResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    v: int = 1
    events: list[StoredEvent]
    next_from_id: int | None = None
    # exactly the non-default params the request supplied (client UX
    # + debugging — confirms the filter was understood)
    filter_applied: dict = {}
