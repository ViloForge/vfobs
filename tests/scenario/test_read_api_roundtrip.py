"""WG2-T5 scenario: the read API end-to-end through the
cluster-deployed vfobs + the in-cluster vtfstub sidecar. Proves
chart + image + VFOBS_VTASKFORGE_URL wiring + ReadAuth(vtf-token
piggyback) + the read endpoints all line up on kind.

Fail-loud (WG1-T6 precedent): this is NOT done unless these run
green end-to-end on the cluster.
"""

import uuid
from datetime import UTC, datetime

import httpx
import pytest

INGEST = "scenario-test-token"
READ_H = {"Authorization": "Bearer any-op-token"}  # vtfstub accepts any


def _sc(wg, task, *, agent=None, es=None, to="done"):
    data = {"from_status": "doing", "to_status": to}
    if es is not None:
        data["execution_summary"] = es
    p = {
        "type": "task.state_changed",
        "v": 1,
        "workgraph_id": wg,
        "task_id": task,
        "source": "scenario",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": data,
    }
    if agent:
        p["agent_id"] = agent
    return p


def _post(port, payload):
    r = httpx.post(
        f"http://localhost:{port}/events",
        json=payload,
        headers={"Authorization": f"Bearer {INGEST}"},
        timeout=30,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.scenario
def test_full_read_path_after_seed(vfobs_port):
    ns = uuid.uuid4().hex[:8]
    wg = f"wg_{ns}"
    ag = f"ag_{ns}"
    # Task ids MUST also be namespaced: the scenario cluster Postgres
    # persists across runs and /tasks/<id> + find_by_task are
    # task-scoped GLOBALLY (not within a workgraph).
    t1, t_rw, t_inflight = f"t1_{ns}", f"trw_{ns}", f"tif_{ns}"
    base = f"http://localhost:{vfobs_port}"

    _post(vfobs_port, _sc(wg, t1, agent=ag,
                          es={"num_turns": 2, "total_tokens": 100,
                              "cost_usd": 0.50}))
    _post(vfobs_port, _sc(wg, t_rw, agent=ag,
                          es={"num_turns": 1, "total_tokens": 10,
                              "cost_usd": 0.10}))
    last_rw = _post(vfobs_port, _sc(wg, t_rw, agent=ag,
                                    es={"num_turns": 5, "total_tokens": 90,
                                        "cost_usd": 0.40}))
    _post(vfobs_port, _sc(wg, t_inflight, to="doing"))  # no summary

    # GET /workgraphs/<id> — vtf metadata from the in-cluster stub
    w = httpx.get(f"{base}/workgraphs/{wg}", headers=READ_H, timeout=30)
    assert w.status_code == 200, w.text
    wb = w.json()
    # vtf metadata is the REAL milestone projection (MilestoneV2Serializer
    # has no `kind` field — verified vtaskforge serializers_v2.py:43).
    # Assert the grounded fields the vtfstub actually returns.
    assert wb["vtf"]["name"] == "Stub Milestone"  # came from vtfstub
    assert wb["vtf"]["status"] == "doing"
    assert wb["vfobs"]["event_count"] == 4
    assert wb["vfobs"]["last_event_id"] >= last_rw

    # GET /tasks/<id> — stub title
    t = httpx.get(f"{base}/tasks/{t_rw}", headers=READ_H, timeout=30).json()
    assert t["vtf"]["title"] == "Stub Task"

    # GET /tasks/<id>/events — StoredEvent {id, event}
    ev = httpx.get(
        f"{base}/tasks/{t_rw}/events", headers=READ_H, timeout=30
    ).json()
    assert len(ev["events"]) == 2
    assert ev["events"][0]["event"]["type"] == "task.state_changed"
    assert all("id" in se for se in ev["events"])

    # GET /events?filter
    f = httpx.get(
        f"{base}/events?workgraph_id={wg}&type_namespace=task",
        headers=READ_H, timeout=30,
    ).json()
    assert len(f["events"]) == 4
    assert f["filter_applied"]["workgraph_id"] == wg

    # GET /workgraphs/<id>/cost — F2 rework de-dup: 0.50 + 0.40 = 0.90
    wc = httpx.get(
        f"{base}/workgraphs/{wg}/cost", headers=READ_H, timeout=30
    ).json()
    assert wc["summary"]["total_cost_usd"] == pytest.approx(0.90)
    assert wc["summary"]["task_count"] == 2  # t1 + t_rw (once)
    assert wc["summary"]["total_tokens"] == 190  # 100 + 90 (latest)

    # GET /agents/<id>/cost
    ac = httpx.get(
        f"{base}/agents/{ag}/cost", headers=READ_H, timeout=30
    ).json()
    assert ac["summary"]["total_cost_usd"] == pytest.approx(0.90)


@pytest.mark.scenario
def test_read_endpoints_require_auth(vfobs_port):
    base = f"http://localhost:{vfobs_port}"
    for path in (
        "/workgraphs/x",
        "/tasks/x",
        "/tasks/x/events",
        "/events",
        "/workgraphs/x/cost",
        "/agents/x/cost",
    ):
        r = httpx.get(f"{base}{path}", timeout=30)
        assert r.status_code == 401, f"{path} -> {r.status_code}"


@pytest.mark.scenario
def test_filter_pagination_e2e(vfobs_port):
    ns = uuid.uuid4().hex[:8]
    wg = f"wgp_{ns}"
    base = f"http://localhost:{vfobs_port}"
    for i in range(250):
        _post(vfobs_port, _sc(wg, f"t{i}", to="doing"))

    page1 = httpx.get(
        f"{base}/events?workgraph_id={wg}&limit=100",
        headers=READ_H, timeout=30,
    ).json()
    assert len(page1["events"]) == 100
    assert page1["next_from_id"] is not None

    page2 = httpx.get(
        f"{base}/events?workgraph_id={wg}&limit=100"
        f"&from_id={page1['next_from_id']}",
        headers=READ_H, timeout=30,
    ).json()
    assert len(page2["events"]) == 100

    page3 = httpx.get(
        f"{base}/events?workgraph_id={wg}&limit=100"
        f"&from_id={page2['next_from_id']}",
        headers=READ_H, timeout=30,
    ).json()
    assert len(page3["events"]) == 50
    assert page3["next_from_id"] is None
