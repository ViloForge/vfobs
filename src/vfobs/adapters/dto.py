"""Typed projections of vtaskforge resources (Adapter pattern).

GROUNDED against the real vtaskforge source (not invented — see
kb feedback-external-contract-grounding). Citations:
- principal: vtaskforge src/prefs/views.py:125 TokenValidationView
  .get → {user_id, username, user_type, is_staff, projects}
- task: src/tasks/serializers_v2.py:30 TaskV2Serializer →
  id, title, description, status, project, workplan, milestone
- milestone (== vfobs "workgraph", D-T1-impl-1):
  src/workplans/serializers_v2.py:43 MilestoneV2Serializer →
  id, name, description, status, order, workplan

All frozen; extra='ignore' so a vtaskforge schema addition can't
break the adapter.
"""

from pydantic import BaseModel, ConfigDict


class VtfPrincipal(BaseModel):
    """Identity from GET /v2/auth/validate/ (200)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    user_id: int | str
    username: str | None = None
    user_type: str | None = None
    is_staff: bool = False


class WorkgraphMetadata(BaseModel):
    """vfobs "workgraph" == vtaskforge milestone. From
    /v2/milestones/<id>/ (MilestoneV2Serializer)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int | str
    name: str | None = None
    status: str | None = None
    description: str | None = None
    order: int | None = None
    workplan: str | int | None = None


class TaskMetadata(BaseModel):
    """From /v2/tasks/<id>/ (TaskV2Serializer)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int | str
    title: str | None = None
    status: str | None = None
    description: str | None = None
