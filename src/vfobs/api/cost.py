"""WG2-T4 cost endpoints. Strategy pattern: one
CostAggregationStrategy impl per aggregation scope, each delegating
to T1's `cost_summary` (which already applies the verifier-F2
latest-per-task de-dup). Pure code; on-the-fly, no caching in v1.
"""

from abc import ABC, abstractmethod

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from vfobs.api.read_auth import Principal, get_read_principal
from vfobs.repositories import CostSummary, EventRepository

router = APIRouter()


class WorkgraphCostResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    v: int = 1
    workgraph_id: str
    summary: CostSummary


class AgentCostResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    v: int = 1
    agent_id: str
    summary: CostSummary


class CostAggregationStrategy(ABC):
    @abstractmethod
    async def compute(self, repo: EventRepository) -> CostSummary: ...

    @abstractmethod
    async def exists(self, repo: EventRepository) -> bool:
        """Whether the scope has ANY events in vfobs (404 gate —
        cost is a pure vfobs view, independent of vtaskforge)."""


class ByWorkgraph(CostAggregationStrategy):
    def __init__(self, workgraph_id: str) -> None:
        self._wid = workgraph_id

    async def compute(self, repo: EventRepository) -> CostSummary:
        return await repo.cost_summary(workgraph_id=self._wid)

    async def exists(self, repo: EventRepository) -> bool:
        return await repo.count_by_workgraph(self._wid) > 0


class ByAgent(CostAggregationStrategy):
    def __init__(self, agent_id: str) -> None:
        self._aid = agent_id

    async def compute(self, repo: EventRepository) -> CostSummary:
        return await repo.cost_summary(agent_id=self._aid)

    async def exists(self, repo: EventRepository) -> bool:
        return bool(await repo.find_filtered(agent_id=self._aid, limit=1))


async def _run(
    strategy: CostAggregationStrategy, repo: EventRepository
) -> CostSummary:
    if not await strategy.exists(repo):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no events for this scope"
        )
    return await strategy.compute(repo)


@router.get(
    "/workgraphs/{workgraph_id}/cost", response_model=WorkgraphCostResponse
)
async def workgraph_cost(
    workgraph_id: str,
    request: Request,
    principal: Principal = Depends(get_read_principal),
) -> WorkgraphCostResponse:
    repo: EventRepository = request.app.state.event_repo
    summary = await _run(ByWorkgraph(workgraph_id), repo)
    return WorkgraphCostResponse(workgraph_id=workgraph_id, summary=summary)


@router.get("/agents/{agent_id}/cost", response_model=AgentCostResponse)
async def agent_cost(
    agent_id: str,
    request: Request,
    principal: Principal = Depends(get_read_principal),
) -> AgentCostResponse:
    repo: EventRepository = request.app.state.event_repo
    summary = await _run(ByAgent(agent_id), repo)
    return AgentCostResponse(agent_id=agent_id, summary=summary)
