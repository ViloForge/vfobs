from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from vfobs.events.base import Event


class ExecutionSummary(BaseModel):
    num_turns: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


class TaskClaimedData(BaseModel):
    claimed_by_agent_id: str


class TaskClaimed(Event):
    type: Literal["task.claimed"] = "task.claimed"
    data: TaskClaimedData


class TaskStateChangedData(BaseModel):
    from_status: str
    to_status: str
    execution_summary: ExecutionSummary | None = None


class TaskStateChanged(Event):
    type: Literal["task.state_changed"] = "task.state_changed"
    data: TaskStateChangedData


class TaskHeartbeatData(BaseModel):
    at: datetime
    current_turn: int | None = None


class TaskHeartbeat(Event):
    type: Literal["task.heartbeat"] = "task.heartbeat"
    data: TaskHeartbeatData


class TaskWorkdirChangedData(BaseModel):
    files_changed: int
    commits: int
    branch: str | None = None


class TaskWorkdirChanged(Event):
    type: Literal["task.workdir_changed"] = "task.workdir_changed"
    data: TaskWorkdirChangedData
