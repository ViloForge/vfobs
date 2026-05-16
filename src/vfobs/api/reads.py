"""WG2-T2 resource endpoints: GET /workgraphs/<id>, /tasks/<id>,
/tasks/<id>/events. Composes the T0 VtfClient Adapter + the T1
EventRepository behind the ReadAuth Strategy dep. No new pattern —
composition. 404 only when BOTH vtaskforge and vfobs have nothing
on the id (asymmetric data returns 200 with the present half).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from vfobs.adapters.vtf import VtfClient
from vfobs.api.dto import (
    TaskEventsResponse,
    TaskReadResponse,
    VfobsPart,
    VtfTaskPart,
    VtfWorkgraphPart,
    WorkgraphReadResponse,
)
from vfobs.api.read_auth import Principal, bearer, get_read_principal
from vfobs.repositories import EventRepository

router = APIRouter()

_MAX_LIMIT = 1000


def _token(creds: HTTPAuthorizationCredentials | None) -> str:
    # ReadAuth already verified the principal; this is the verified
    # token, passed through to vtaskforge for resource metadata.
    return creds.credentials if creds else ""


@router.get("/workgraphs/{workgraph_id}", response_model=WorkgraphReadResponse)
async def get_workgraph(
    workgraph_id: str,
    request: Request,
    principal: Principal = Depends(get_read_principal),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> WorkgraphReadResponse:
    vtf: VtfClient | None = request.app.state.vtf_client
    repo: EventRepository = request.app.state.event_repo
    vtf_meta = (
        await vtf.get_workgraph(workgraph_id, _token(creds)) if vtf else None
    )
    count = await repo.count_by_workgraph(workgraph_id)
    if vtf_meta is None and count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workgraph not found")
    tail = await repo.find_last_by_workgraph(workgraph_id)
    return WorkgraphReadResponse(
        workgraph_id=workgraph_id,
        vtf=VtfWorkgraphPart.from_metadata(vtf_meta) if vtf_meta else None,
        vfobs=VfobsPart.build(count, tail),
    )


@router.get("/tasks/{task_id}", response_model=TaskReadResponse)
async def get_task(
    task_id: str,
    request: Request,
    principal: Principal = Depends(get_read_principal),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> TaskReadResponse:
    vtf: VtfClient | None = request.app.state.vtf_client
    repo: EventRepository = request.app.state.event_repo
    vtf_meta = await vtf.get_task(task_id, _token(creds)) if vtf else None
    count = await repo.count_by_task(task_id)
    if vtf_meta is None and count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    tail = await repo.find_last_by_task(task_id)
    return TaskReadResponse(
        task_id=task_id,
        vtf=VtfTaskPart.from_metadata(vtf_meta) if vtf_meta else None,
        vfobs=VfobsPart.build(count, tail),
    )


@router.get("/tasks/{task_id}/events", response_model=TaskEventsResponse)
async def get_task_events(
    task_id: str,
    request: Request,
    from_id: int | None = None,
    limit: int = 100,
    principal: Principal = Depends(get_read_principal),
) -> TaskEventsResponse:
    repo: EventRepository = request.app.state.event_repo
    page = await repo.find_by_task(task_id, from_id=from_id, limit=limit)
    requested = max(1, min(limit, _MAX_LIMIT))
    next_from_id = (
        page[-1].id + 1 if len(page) == requested and page else None
    )
    return TaskEventsResponse(
        task_id=task_id, events=page, next_from_id=next_from_id
    )
