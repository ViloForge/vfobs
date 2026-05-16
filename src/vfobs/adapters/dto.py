"""Typed projections of vtaskforge resources (Adapter pattern, plan §D2).

vfobs deliberately does NOT mirror vtaskforge's full schema — these
models capture only the fields the WG2 read endpoints surface. All
frozen (R13: every key declared; no undeclared-key mutation anywhere
downstream).
"""

from pydantic import BaseModel, ConfigDict


class WhoamiPrincipal(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    display_name: str | None = None


class WorkgraphMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: str
    kind: str | None = None
    target_repos: list[str] = []
    tags: list[str] = []
    created_at: str | None = None  # ISO 8601


class TaskMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    workgraph_id: str | None = None
    status: str
    title: str | None = None
    created_at: str | None = None  # ISO 8601
