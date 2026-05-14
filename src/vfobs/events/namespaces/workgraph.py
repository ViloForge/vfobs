from typing import Literal

from pydantic import BaseModel

from vfobs.events.base import Event


class WorkgraphCreatedData(BaseModel):
    created_by: str
    kind: str
    target_repos: list[str]


class WorkgraphCreated(Event):
    type: Literal["workgraph.created"] = "workgraph.created"
    data: WorkgraphCreatedData


class WorkgraphStateChangedData(BaseModel):
    from_status: str
    to_status: str


class WorkgraphStateChanged(Event):
    type: Literal["workgraph.state_changed"] = "workgraph.state_changed"
    data: WorkgraphStateChangedData


class WorkgraphCompletedData(BaseModel):
    terminal_status: str
    task_count: int


class WorkgraphCompleted(Event):
    type: Literal["workgraph.completed"] = "workgraph.completed"
    data: WorkgraphCompletedData
