"""Tiny in-cluster vtaskforge stub for the WG2 scenario. Exists ONLY
so the deployed vfobs VtfClient has a real network target — it does
NOT verify vfobs-vs-real-vtaskforge agreement (that's a WG5+ canary).
Any non-empty bearer is accepted (whoami). Dependency-free beyond
FastAPI + uvicorn.
"""

from fastapi import FastAPI, Header

app = FastAPI(title="vtfstub")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/v2/auth/whoami")
def whoami(authorization: str = Header(default="")) -> dict:
    return {"user_id": "stub-operator", "display_name": "Stub Operator"}


@app.get("/v2/workgraphs/{workgraph_id}/")
def get_workgraph(workgraph_id: str) -> dict:
    return {
        "id": workgraph_id,
        "status": "doing",
        "kind": "infrastructure",
        "target_repos": ["viloforge/vfobs"],
        "tags": [],
    }


@app.get("/v2/tasks/{task_id}/")
def get_task(task_id: str) -> dict:
    return {
        "id": task_id,
        "workgraph_id": "wg_scenario_read",
        "status": "doing",
        "title": "Stub Task",
    }
