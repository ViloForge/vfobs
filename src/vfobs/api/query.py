"""WG2-T3 Builder: one place where URL params become a typed,
validated EventQuery. Unknown params / out-of-range values are
rejected as 422 (never silently accepted).
"""

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_HTTP_422 = 422  # literal: starlette deprecated the *_ENTITY constant
# name and the *_CONTENT replacement isn't in our pinned version


class EventQuery(BaseModel):
    # extra='forbid' => unknown query params raise (→ 422), not
    # silently ignored (FastAPI's default for stray query params).
    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True
    )

    workgraph_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    type_: str | None = Field(default=None, alias="type")
    type_namespace: str | None = None
    org_id: str = "viloforge"  # extensibility hook (default => excluded)
    from_id: int | None = Field(default=None, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)


def build_event_query(request: Request) -> EventQuery:
    """Builder: raw query string → validated EventQuery. Any
    validation failure (unknown param, limit>1000, from_id<0, bad
    int) is a 422 with the pydantic error detail."""
    raw = dict(request.query_params)
    try:
        return EventQuery.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(
            _HTTP_422,
            detail=e.errors(include_url=False, include_context=False),
        ) from None
