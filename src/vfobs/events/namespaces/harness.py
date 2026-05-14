from typing import Literal

from pydantic import BaseModel

from vfobs.events.base import Event


class HarnessTurnStartedData(BaseModel):
    turn_number: int
    model: str
    prompt_tokens: int | None = None


class HarnessTurnStarted(Event):
    type: Literal["harness.turn_started"] = "harness.turn_started"
    data: HarnessTurnStartedData


class HarnessToolCallData(BaseModel):
    turn_number: int
    tool_name: str
    tool_args_summary: str | None = None


class HarnessToolCall(Event):
    type: Literal["harness.tool_call"] = "harness.tool_call"
    data: HarnessToolCallData


class HarnessTurnCompletedData(BaseModel):
    turn_number: int
    completion_tokens: int | None = None
    duration_ms: int | None = None


class HarnessTurnCompleted(Event):
    type: Literal["harness.turn_completed"] = "harness.turn_completed"
    data: HarnessTurnCompletedData
