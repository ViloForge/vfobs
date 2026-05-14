from typing import Literal

from pydantic import BaseModel

from vfobs.events.base import Event


class JudgeStartedData(BaseModel):
    judge_agent_id: str


class JudgeStarted(Event):
    type: Literal["judge.started"] = "judge.started"
    data: JudgeStartedData


class JudgeReviewSubmittedData(BaseModel):
    per_ac_verdicts: dict[str, str]


class JudgeReviewSubmitted(Event):
    type: Literal["judge.review_submitted"] = "judge.review_submitted"
    data: JudgeReviewSubmittedData


class JudgeDecisionData(BaseModel):
    decision: Literal["approved", "changes_requested", "rejected"]
    notes: str | None = None


class JudgeDecision(Event):
    type: Literal["judge.decision"] = "judge.decision"
    data: JudgeDecisionData
