from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from vfobs.events.base import Event


class AnomalyStuckDetectedData(BaseModel):
    last_activity_at: datetime
    t_m_seconds: int
    last_seen_event_type: str | None = None


class AnomalyStuckDetected(Event):
    type: Literal["anomaly.stuck_detected"] = "anomaly.stuck_detected"
    data: AnomalyStuckDetectedData
