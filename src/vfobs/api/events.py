from collections.abc import Callable, Awaitable
from typing import Annotated, Union

from fastapi import APIRouter, Depends, Request, status
from pydantic import Field

from vfobs.api.auth import get_principal
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

router = APIRouter()

# Discriminated union — FastAPI/Pydantic dispatches by the literal `type`.
AnyEvent = Annotated[
    Union[
        WorkgraphCreated,
        WorkgraphStateChanged,
        WorkgraphCompleted,
        TaskClaimed,
        TaskStateChanged,
        TaskHeartbeat,
        TaskWorkdirChanged,
        HarnessTurnStarted,
        HarnessToolCall,
        HarnessTurnCompleted,
        GateStarted,
        GatePassed,
        GateFailed,
        JudgeStarted,
        JudgeReviewSubmitted,
        JudgeDecision,
        AnomalyStuckDetected,
    ],
    Field(discriminator="type"),
]


# ---- Chain of Responsibility nodes -----------------------------------------

PipelineNode = Callable[[Event, dict], Awaitable[Event]]


async def enricher(event: Event, context: dict) -> Event:
    """v1 no-op pass-through. Extension point for v2 Python-side
    enrichments (geo-tagging, tenant resolution, classification
    overrides). Server-time audit lives in `events.created_at` (T0),
    not in `event.data` — see plan §D6 + verifier-findings F1."""
    return event


async def storer(event: Event, context: dict) -> Event:
    repo = context["repo"]
    eid = await repo.store(event)
    context["id"] = eid
    return event


PIPELINE: list[PipelineNode] = [enricher, storer]


async def run_pipeline(event: Event, context: dict, pipeline: list[PipelineNode] | None = None) -> int:
    nodes = pipeline if pipeline is not None else PIPELINE
    current = event
    for node in nodes:
        current = await node(current, context)
    return int(context["id"])


# ---- Endpoint ---------------------------------------------------------------


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def post_events(
    request: Request,
    body: AnyEvent,
    principal: str = Depends(get_principal),
) -> dict:
    context = {
        "repo": request.app.state.event_repo,
        "principal": principal,
    }
    eid = await run_pipeline(body, context)
    return {"id": eid}
