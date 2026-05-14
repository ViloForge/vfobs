from vfobs.events.base import Event
from vfobs.events.namespaces.anomaly import AnomalyStuckDetected
from vfobs.events.namespaces.gate import GateFailed, GatePassed, GateStarted
from vfobs.events.namespaces.harness import (
    HarnessToolCall,
    HarnessTurnCompleted,
    HarnessTurnStarted,
)
from vfobs.events.namespaces.judge import (
    JudgeDecision,
    JudgeReviewSubmitted,
    JudgeStarted,
)
from vfobs.events.namespaces.task import (
    TaskClaimed,
    TaskHeartbeat,
    TaskStateChanged,
    TaskWorkdirChanged,
)
from vfobs.events.namespaces.workgraph import (
    WorkgraphCompleted,
    WorkgraphCreated,
    WorkgraphStateChanged,
)

EVENT_CLASSES: list[type[Event]] = [
    AnomalyStuckDetected,
    GateFailed,
    GatePassed,
    GateStarted,
    HarnessToolCall,
    HarnessTurnCompleted,
    HarnessTurnStarted,
    JudgeDecision,
    JudgeReviewSubmitted,
    JudgeStarted,
    TaskClaimed,
    TaskHeartbeat,
    TaskStateChanged,
    TaskWorkdirChanged,
    WorkgraphCompleted,
    WorkgraphCreated,
    WorkgraphStateChanged,
]


def _type_value(cls: type[Event]) -> str:
    return cls.model_fields["type"].default  # type: ignore[no-any-return]


def dump_event_schemas() -> dict[str, dict]:
    """Return a stable, sorted mapping of event_type -> JSON Schema.

    Output is suitable for committing to a contract-test fixture; the
    fixture pins v1's public schema per NFR1.
    """
    out: dict[str, dict] = {}
    for cls in EVENT_CLASSES:
        out[_type_value(cls)] = cls.model_json_schema()
    return dict(sorted(out.items()))
