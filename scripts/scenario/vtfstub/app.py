"""Tiny in-cluster vtaskforge stub for the WG2/WG5 scenario.

DERIVED FROM THE REAL vtaskforge CONTRACT (kb
feedback-external-contract-grounding) — NOT invented:
- DRF `Authorization: Token <t>` scheme (vtf-sdk transport.py:58)
- GET /v2/auth/validate/  (src/prefs/views.py:100; 200 identity /
  401 invalid) — the real token-validation endpoint
- GET /v2/tasks/<id>/      (TaskV2Serializer)
- GET /v2/milestones/<id>/ (MilestoneV2Serializer; vfobs
  "workgraph" == vtaskforge milestone)

It exists ONLY to give VtfClient a real-shaped network target in
the kind scenario; real auth behaviour is verified in unit +
integration against MockTransport/ASGI. A non-`Token ` header or
the literal "Token bad" → 401 (models DRF IsAuthenticated).
"""

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse

app = FastAPI(title="vtfstub")


def _authed(authorization: str | None) -> bool:
    if not authorization or not authorization.startswith("Token "):
        return False
    return authorization != "Token bad"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/v2/auth/validate/")
def validate(authorization: str = Header(default="")):
    if not _authed(authorization):
        return JSONResponse({"detail": "Invalid token."}, status_code=401)
    return {
        "user_id": 1,
        "username": "stub-operator",
        "user_type": "human",
        "is_staff": False,
        "projects": [],
    }


@app.get("/v2/tasks/{task_id}/")
def get_task(task_id: str, authorization: str = Header(default="")):
    if not _authed(authorization):
        return JSONResponse({"detail": "Invalid token."}, status_code=401)
    return {"id": task_id, "title": "Stub Task", "status": "doing"}


@app.get("/v2/milestones/{milestone_id}/")
def get_milestone(milestone_id: str, authorization: str = Header(default="")):
    if not _authed(authorization):
        return JSONResponse({"detail": "Invalid token."}, status_code=401)
    return {
        "id": milestone_id,
        "name": "Stub Milestone",
        "status": "doing",
        "order": 0,
    }
