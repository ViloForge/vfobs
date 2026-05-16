"""Vendored minimal event models for the types the Emitter sends.

Deviation D-T0sdk-1 (vs verifier F-adv2 "import the WG1 models"):
the SDK MUST install standalone for clients (vafi) without the
vfobs *server* package — importing `vfobs.events` would invert the
dependency (SDK → server). So the envelope is vendored here,
mirroring WG1 `src/vfobs/events/` exactly. The wire-compatibility
backstop F-adv2 itself relied on is `tests/contract/
test_emitter_envelope.py`, which jsonschema-validates every
emitted payload against WG1's locked `event_schemas.v1.json`.
Vendor drift is therefore caught at build, not in production.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_VALID_NAMESPACES = {
    "workgraph", "task", "harness", "gate", "judge", "anomaly",
}


class Classification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SECRET = "secret"


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

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
    def _ns(cls, v: str) -> str:
        if v.partition(".")[0] not in _VALID_NAMESPACES:
            raise ValueError(f"unknown namespace in event type '{v}'")
        return v


class _ClaimedData(BaseModel):
    claimed_by_agent_id: str


class _HeartbeatData(BaseModel):
    at: datetime
    current_turn: int | None = None


class ExecutionSummary(BaseModel):
    num_turns: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


class _StateChangedData(BaseModel):
    from_status: str
    to_status: str
    execution_summary: ExecutionSummary | None = None


class _TurnStartedData(BaseModel):
    turn_number: int
    model: str
    prompt_tokens: int | None = None


class _TurnCompletedData(BaseModel):
    turn_number: int
    completion_tokens: int | None = None
    duration_ms: int | None = None


class _WorkdirChangedData(BaseModel):
    files_changed: int
    commits: int
    branch: str | None = None


class TaskClaimed(Event):
    type: Literal["task.claimed"] = "task.claimed"
    data: _ClaimedData


class TaskHeartbeat(Event):
    type: Literal["task.heartbeat"] = "task.heartbeat"
    data: _HeartbeatData


class TaskStateChanged(Event):
    type: Literal["task.state_changed"] = "task.state_changed"
    data: _StateChangedData


class HarnessTurnStarted(Event):
    type: Literal["harness.turn_started"] = "harness.turn_started"
    data: _TurnStartedData


class HarnessTurnCompleted(Event):
    type: Literal["harness.turn_completed"] = "harness.turn_completed"
    data: _TurnCompletedData


class TaskWorkdirChanged(Event):
    type: Literal["task.workdir_changed"] = "task.workdir_changed"
    data: _WorkdirChangedData


def _now(ts: datetime | None) -> datetime:
    from datetime import UTC
    return ts or datetime.now(UTC)


def task_claimed(
    *, workgraph_id: str, task_id: str, source: str,
    claimed_by_agent_id: str, timestamp: datetime | None = None, **base,
) -> TaskClaimed:
    return TaskClaimed(
        workgraph_id=workgraph_id, task_id=task_id, source=source,
        timestamp=_now(timestamp),
        data=_ClaimedData(claimed_by_agent_id=claimed_by_agent_id),
        **base,
    )


def task_heartbeat(
    *, workgraph_id: str, task_id: str, source: str,
    current_turn: int | None = None, timestamp: datetime | None = None,
    **base,
) -> TaskHeartbeat:
    at = _now(timestamp)
    return TaskHeartbeat(
        workgraph_id=workgraph_id, task_id=task_id, source=source,
        timestamp=at, data=_HeartbeatData(at=at, current_turn=current_turn),
        **base,
    )


def task_state_changed(
    *, workgraph_id: str, task_id: str, source: str,
    from_status: str, to_status: str,
    execution_summary: ExecutionSummary | None = None,
    timestamp: datetime | None = None, **base,
) -> TaskStateChanged:
    return TaskStateChanged(
        workgraph_id=workgraph_id, task_id=task_id, source=source,
        timestamp=_now(timestamp),
        data=_StateChangedData(
            from_status=from_status, to_status=to_status,
            execution_summary=execution_summary,
        ),
        **base,
    )


def harness_turn_started(
    *, workgraph_id: str, task_id: str, source: str,
    turn_number: int, model: str, prompt_tokens: int | None = None,
    timestamp: datetime | None = None, **base,
) -> HarnessTurnStarted:
    return HarnessTurnStarted(
        workgraph_id=workgraph_id, task_id=task_id, source=source,
        timestamp=_now(timestamp),
        data=_TurnStartedData(
            turn_number=turn_number, model=model,
            prompt_tokens=prompt_tokens,
        ),
        **base,
    )


def harness_turn_completed(
    *, workgraph_id: str, task_id: str, source: str,
    turn_number: int, completion_tokens: int | None = None,
    duration_ms: int | None = None, timestamp: datetime | None = None,
    **base,
) -> HarnessTurnCompleted:
    return HarnessTurnCompleted(
        workgraph_id=workgraph_id, task_id=task_id, source=source,
        timestamp=_now(timestamp),
        data=_TurnCompletedData(
            turn_number=turn_number,
            completion_tokens=completion_tokens, duration_ms=duration_ms,
        ),
        **base,
    )


def task_workdir_changed(
    *, workgraph_id: str, task_id: str, source: str,
    files_changed: int, commits: int, branch: str | None = None,
    timestamp: datetime | None = None, **base,
) -> TaskWorkdirChanged:
    return TaskWorkdirChanged(
        workgraph_id=workgraph_id, task_id=task_id, source=source,
        timestamp=_now(timestamp),
        data=_WorkdirChangedData(
            files_changed=files_changed, commits=commits, branch=branch,
        ),
        **base,
    )
