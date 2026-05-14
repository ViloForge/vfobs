from typing import Literal

from pydantic import BaseModel

from vfobs.events.base import Event


class GateStartedData(BaseModel):
    gate_name: str
    command: str


class GateStarted(Event):
    type: Literal["gate.started"] = "gate.started"
    data: GateStartedData


class GatePassedData(BaseModel):
    gate_name: str
    duration_ms: int | None = None


class GatePassed(Event):
    type: Literal["gate.passed"] = "gate.passed"
    data: GatePassedData


class GateFailedData(BaseModel):
    gate_name: str
    exit_code: int
    stderr_tail: str | None = None


class GateFailed(Event):
    type: Literal["gate.failed"] = "gate.failed"
    data: GateFailedData
