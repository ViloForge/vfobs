from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from vfobs.api.auth import StaticTokenAuth
from vfobs.config import Settings
from vfobs.events import EventFactory
from vfobs.main import create_app
from vfobs.repositories import InMemoryEventRepository

TOKEN = "contract-token"


def _build_app():
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        ingest_token=SecretStr(TOKEN),
    )
    repo = InMemoryEventRepository()
    auth = StaticTokenAuth(settings)
    app = create_app(settings, event_repo=repo, ingest_auth=auth)
    app.state.engine = None
    return app, repo


def _all_seventeen_events():
    """Construct one of every event type via the factory — drift between
    T1's event types and what the write API accepts is caught here."""
    wg, tk, src = "wg_ct", "t_ct", "contract"
    now = datetime.now(UTC)
    return [
        EventFactory.workgraph_created(workgraph_id=wg, source=src, created_by="op", kind="bugfix", target_repos=["r"], timestamp=now),
        EventFactory.workgraph_state_changed(workgraph_id=wg, source=src, from_status="a", to_status="b", timestamp=now),
        EventFactory.workgraph_completed(workgraph_id=wg, source=src, terminal_status="done", task_count=3, timestamp=now),
        EventFactory.task_claimed(workgraph_id=wg, task_id=tk, source=src, claimed_by_agent_id="ag", timestamp=now),
        EventFactory.task_state_changed(workgraph_id=wg, task_id=tk, source=src, from_status="a", to_status="b", timestamp=now),
        EventFactory.task_heartbeat(workgraph_id=wg, task_id=tk, source=src, timestamp=now),
        EventFactory.task_workdir_changed(workgraph_id=wg, task_id=tk, source=src, files_changed=1, commits=0, timestamp=now),
        EventFactory.harness_turn_started(workgraph_id=wg, task_id=tk, source=src, turn_number=1, model="m", timestamp=now),
        EventFactory.harness_tool_call(workgraph_id=wg, task_id=tk, source=src, turn_number=1, tool_name="Read", timestamp=now),
        EventFactory.harness_turn_completed(workgraph_id=wg, task_id=tk, source=src, turn_number=1, timestamp=now),
        EventFactory.gate_started(workgraph_id=wg, task_id=tk, source=src, gate_name="g", command="cmd", timestamp=now),
        EventFactory.gate_passed(workgraph_id=wg, task_id=tk, source=src, gate_name="g", timestamp=now),
        EventFactory.gate_failed(workgraph_id=wg, task_id=tk, source=src, gate_name="g", exit_code=1, timestamp=now),
        EventFactory.judge_started(workgraph_id=wg, task_id=tk, source=src, judge_agent_id="ag_j", timestamp=now),
        EventFactory.judge_review_submitted(workgraph_id=wg, task_id=tk, source=src, per_ac_verdicts={"AC-1": "passed"}, timestamp=now),
        EventFactory.judge_decision(workgraph_id=wg, task_id=tk, source=src, decision="approved", timestamp=now),
        EventFactory.anomaly_stuck_detected(workgraph_id=wg, task_id=tk, source="detector", last_activity_at=now, t_m_seconds=180, timestamp=now),
    ]


@pytest.mark.contract
def test_each_of_17_event_types_round_trips_through_post():
    app, repo = _build_app()
    events = _all_seventeen_events()
    assert len(events) == 17
    with TestClient(app) as client:
        ids: list[int] = []
        for e in events:
            payload = e.model_dump(mode="json")
            resp = client.post(
                "/events",
                json=payload,
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert resp.status_code == 201, f"event {e.type} rejected: {resp.text}"
            ids.append(resp.json()["id"])
    # monotonic ids
    assert ids == sorted(ids)
    assert len(set(ids)) == 17
