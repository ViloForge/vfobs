from datetime import UTC, datetime, timedelta

import httpx
import psycopg
import pytest

TOKEN = "scenario-test-token"


@pytest.mark.scenario
def test_post_event_persists_and_retrievable(vfobs_port, pg_port):
    """End-to-end: POST through the cluster-deployed vfobs, then read
    the row directly from Postgres. Proves the chart + image + secrets
    + service mesh + write-API + repository all line up."""
    payload = {
        "type": "task.state_changed",
        "v": 1,
        "workgraph_id": "wg_scenario1",
        "task_id": "t_scenario",
        "source": "scenario-test",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"from_status": "todo", "to_status": "doing"},
    }
    before = datetime.now(UTC)
    resp = httpx.post(
        f"http://localhost:{vfobs_port}/events",
        json=payload,
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=30,
    )
    assert resp.status_code == 201, resp.text
    eid = resp.json()["id"]
    assert isinstance(eid, int) and eid > 0

    with psycopg.connect(
        f"host=localhost port={pg_port} user=vfobs_app password=devpassword dbname=vfobs"
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT type, workgraph_id, task_id, data, created_at "
                "FROM vfobs.events WHERE id = %s",
                (eid,),
            )
            row = cur.fetchone()
    assert row is not None
    typ, wgid, tid, data, created_at = row
    assert typ == "task.state_changed"
    assert wgid == "wg_scenario1"
    assert tid == "t_scenario"
    assert data["from_status"] == "todo"
    assert data["to_status"] == "doing"
    # server-time audit: created_at populated by Postgres DEFAULT now()
    delta = created_at - before
    assert timedelta(seconds=-1) <= delta <= timedelta(seconds=30)


@pytest.mark.scenario
def test_health_endpoints_reachable_through_chart(vfobs_port):
    h = httpx.get(f"http://localhost:{vfobs_port}/healthz", timeout=10)
    assert h.status_code == 200
    assert h.json() == {"status": "ok"}

    r = httpx.get(f"http://localhost:{vfobs_port}/readyz", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


@pytest.mark.scenario
def test_unauthorized_post_rejected(vfobs_port):
    payload = {
        "type": "task.heartbeat",
        "v": 1,
        "workgraph_id": "wg_scenario1",
        "task_id": "t_scenario",
        "source": "scenario-test",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"at": datetime.now(UTC).isoformat()},
    }
    # no Authorization header
    r1 = httpx.post(f"http://localhost:{vfobs_port}/events", json=payload, timeout=10)
    assert r1.status_code == 401

    # wrong token
    r2 = httpx.post(
        f"http://localhost:{vfobs_port}/events",
        json=payload,
        headers={"Authorization": "Bearer wrong-token"},
        timeout=10,
    )
    assert r2.status_code == 401
