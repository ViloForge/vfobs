from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventNamespace(str, Enum):
    WORKGRAPH = "workgraph"
    TASK = "task"
    HARNESS = "harness"
    GATE = "gate"
    JUDGE = "judge"
    ANOMALY = "anomaly"


class Classification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SECRET = "secret"


_VALID_NAMESPACES = {n.value for n in EventNamespace}


class Event(BaseModel):
    """Base for every vfobs event. Concrete subclasses fix `type` to a
    Literal and define a typed `data` sub-model."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    # NOTE (verifier F1, mechanism R2): the DB id is deliberately NOT
    # on Event. Event is the write/ingest wire model and its v1 schema
    # is locked (tests/fixtures/event_schemas.v1.json). The stored id
    # is read-side metadata — it rides on the StoredEvent read model
    # (repositories.StoredEvent) returned by find_*, never polluting
    # the ingest contract.
    v: int = 1
    type: str
    workgraph_id: str = Field(min_length=1)
    task_id: str | None = None
    agent_id: str | None = None
    trace_id: str | None = None
    source: str = Field(min_length=1)
    timestamp: datetime
    classification: Classification = Classification.INTERNAL
    org_id: str = "viloforge"
    cluster_id: str = "vafi-dev"

    @field_validator("type")
    @classmethod
    def _type_has_known_namespace(cls, v: str) -> str:
        ns, _, _ = v.partition(".")
        if ns not in _VALID_NAMESPACES:
            raise ValueError(
                f"event type '{v}' has unknown namespace '{ns}'; "
                f"expected one of {sorted(_VALID_NAMESPACES)}"
            )
        return v
