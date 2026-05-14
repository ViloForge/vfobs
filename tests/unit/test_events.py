from datetime import datetime, UTC

import pytest
from pydantic import ValidationError

from vfobs.events import Classification, EventFactory
from vfobs.events.namespaces.anomaly import AnomalyStuckDetected
from vfobs.events.namespaces.gate import GateFailed, GatePassed, GateStarted
from vfobs.events.namespaces.harness import (
    HarnessToolCall,
    HarnessTurnCompleted,
    HarnessTurnStarted,
)
from vfobs.events.namespaces.judge import (
    JudgeDecision,
    JudgeReviewSubmitted,
    JudgeStarted,
)
from vfobs.events.namespaces.task import (
    ExecutionSummary,
    TaskClaimed,
    TaskHeartbeat,
    TaskStateChanged,
    TaskWorkdirChanged,
)
from vfobs.events.namespaces.workgraph import (
    WorkgraphCompleted,
    WorkgraphCreated,
    WorkgraphStateChanged,
)
from vfobs.events.schema import EVENT_CLASSES, dump_event_schemas

WG = "wg_test"
TASK = "t_test"
SRC = "vfobs-test"


# ---- construction happy paths -----------------------------------------------


@pytest.mark.unit
def test_factory_workgraph_created():
    e = EventFactory.workgraph_created(
        workgraph_id=WG,
        source=SRC,
        created_by="op",
        kind="bugfix",
        target_repos=["a", "b"],
    )
    assert isinstance(e, WorkgraphCreated)
    assert e.type == "workgraph.created"
    assert e.v == 1
    assert e.org_id == "viloforge"
    assert e.cluster_id == "vafi-dev"
    assert e.classification == Classification.INTERNAL
    assert e.data.target_repos == ["a", "b"]


@pytest.mark.unit
def test_factory_workgraph_state_changed():
    e = EventFactory.workgraph_state_changed(
        workgraph_id=WG, source=SRC, from_status="draft", to_status="ready"
    )
    assert isinstance(e, WorkgraphStateChanged)
    assert e.data.from_status == "draft" and e.data.to_status == "ready"


@pytest.mark.unit
def test_factory_workgraph_completed():
    e = EventFactory.workgraph_completed(
        workgraph_id=WG, source=SRC, terminal_status="done", task_count=7
    )
    assert isinstance(e, WorkgraphCompleted)
    assert e.data.task_count == 7


@pytest.mark.unit
def test_factory_task_claimed():
    e = EventFactory.task_claimed(
        workgraph_id=WG, task_id=TASK, source=SRC, claimed_by_agent_id="ag_1"
    )
    assert isinstance(e, TaskClaimed)
    assert e.data.claimed_by_agent_id == "ag_1"


@pytest.mark.unit
def test_factory_task_state_changed_with_summary():
    es = ExecutionSummary(num_turns=4, total_tokens=1234, cost_usd=0.05)
    e = EventFactory.task_state_changed(
        workgraph_id=WG,
        task_id=TASK,
        source=SRC,
        from_status="doing",
        to_status="done",
        execution_summary=es,
    )
    assert isinstance(e, TaskStateChanged)
    assert e.data.execution_summary is not None
    assert e.data.execution_summary.cost_usd == 0.05


@pytest.mark.unit
def test_factory_task_heartbeat_defaults_at():
    e = EventFactory.task_heartbeat(workgraph_id=WG, task_id=TASK, source=SRC)
    assert isinstance(e, TaskHeartbeat)
    assert e.data.at is not None


@pytest.mark.unit
def test_factory_task_workdir_changed():
    e = EventFactory.task_workdir_changed(
        workgraph_id=WG,
        task_id=TASK,
        source=SRC,
        files_changed=3,
        commits=1,
        branch="main",
    )
    assert isinstance(e, TaskWorkdirChanged)
    assert e.data.files_changed == 3


@pytest.mark.unit
@pytest.mark.parametrize(
    "method,kwargs,cls",
    [
        (
            "harness_turn_started",
            {"turn_number": 1, "model": "claude-opus-4-7"},
            HarnessTurnStarted,
        ),
        (
            "harness_tool_call",
            {"turn_number": 1, "tool_name": "Read"},
            HarnessToolCall,
        ),
        (
            "harness_turn_completed",
            {"turn_number": 1, "completion_tokens": 500},
            HarnessTurnCompleted,
        ),
    ],
)
def test_factory_harness(method, kwargs, cls):
    fn = getattr(EventFactory, method)
    e = fn(workgraph_id=WG, task_id=TASK, source=SRC, **kwargs)
    assert isinstance(e, cls)


@pytest.mark.unit
def test_factory_gate_lifecycle():
    started = EventFactory.gate_started(
        workgraph_id=WG, task_id=TASK, source=SRC, gate_name="branch-exists", command="git ls-remote ..."
    )
    passed = EventFactory.gate_passed(
        workgraph_id=WG, task_id=TASK, source=SRC, gate_name="branch-exists", duration_ms=42
    )
    failed = EventFactory.gate_failed(
        workgraph_id=WG, task_id=TASK, source=SRC, gate_name="branch-exists", exit_code=1, stderr_tail="..."
    )
    assert isinstance(started, GateStarted)
    assert isinstance(passed, GatePassed)
    assert isinstance(failed, GateFailed)


@pytest.mark.unit
def test_factory_judge_lifecycle():
    j0 = EventFactory.judge_started(
        workgraph_id=WG, task_id=TASK, source=SRC, judge_agent_id="ag_j"
    )
    j1 = EventFactory.judge_review_submitted(
        workgraph_id=WG, task_id=TASK, source=SRC, per_ac_verdicts={"AC-1": "passed"}
    )
    j2 = EventFactory.judge_decision(
        workgraph_id=WG, task_id=TASK, source=SRC, decision="approved"
    )
    assert isinstance(j0, JudgeStarted)
    assert isinstance(j1, JudgeReviewSubmitted)
    assert isinstance(j2, JudgeDecision)
    assert j2.data.decision == "approved"


@pytest.mark.unit
def test_factory_anomaly_stuck_detected():
    e = EventFactory.anomaly_stuck_detected(
        workgraph_id=WG,
        task_id=TASK,
        source="vfobs-stuck-detector",
        last_activity_at=datetime.now(UTC),
        t_m_seconds=180,
    )
    assert isinstance(e, AnomalyStuckDetected)
    assert e.data.t_m_seconds == 180


# ---- failure paths ----------------------------------------------------------


@pytest.mark.unit
def test_event_rejects_missing_required_field():
    with pytest.raises(ValidationError):
        TaskClaimed(  # missing required fields
            type="task.claimed",  # type: ignore[arg-type]
        )  # type: ignore[call-arg]


@pytest.mark.unit
def test_event_rejects_bad_classification():
    with pytest.raises(ValidationError):
        EventFactory.workgraph_state_changed(
            workgraph_id=WG,
            source=SRC,
            from_status="a",
            to_status="b",
            classification="bogus",  # not a Classification enum value
        )


@pytest.mark.unit
def test_event_rejects_bad_type_namespace():
    """The Event base validator rejects unknown namespaces. Concrete
    subclasses fix `type` to a Literal so direct misuse is not possible;
    the base validator is the safety net for any raw construction."""
    from vfobs.events.base import Event

    with pytest.raises(ValidationError):
        Event(
            type="bogus.thing",
            workgraph_id=WG,
            source=SRC,
            timestamp=datetime.now(UTC),
        )


@pytest.mark.unit
def test_concrete_event_rejects_wrong_type_literal():
    with pytest.raises(ValidationError):
        TaskClaimed.model_validate(
            {
                "type": "task.state_changed",  # wrong literal for this class
                "workgraph_id": WG,
                "task_id": TASK,
                "source": SRC,
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {"claimed_by_agent_id": "ag_1"},
            }
        )


@pytest.mark.unit
def test_event_is_frozen():
    e = EventFactory.task_claimed(
        workgraph_id=WG, task_id=TASK, source=SRC, claimed_by_agent_id="ag_1"
    )
    with pytest.raises(ValidationError):
        e.source = "tampered"  # type: ignore[misc]


# ---- schema export ----------------------------------------------------------


@pytest.mark.unit
def test_dump_event_schemas_covers_17_types():
    schemas = dump_event_schemas()
    assert len(schemas) == 17
    expected = {
        "workgraph.created",
        "workgraph.state_changed",
        "workgraph.completed",
        "task.claimed",
        "task.state_changed",
        "task.heartbeat",
        "task.workdir_changed",
        "harness.turn_started",
        "harness.tool_call",
        "harness.turn_completed",
        "gate.started",
        "gate.passed",
        "gate.failed",
        "judge.started",
        "judge.review_submitted",
        "judge.decision",
        "anomaly.stuck_detected",
    }
    assert set(schemas.keys()) == expected


@pytest.mark.unit
def test_dump_event_schemas_keys_are_sorted():
    schemas = dump_event_schemas()
    keys = list(schemas.keys())
    assert keys == sorted(keys)


@pytest.mark.unit
def test_event_classes_count_matches_namespaces():
    assert len(EVENT_CLASSES) == 17


# ---- extensibility AC -------------------------------------------------------


@pytest.mark.unit
def test_add_new_event_type_follows_pattern():
    """Documents the extension recipe: define a Data BaseModel + concrete
    Event subclass with `type: Literal[...]`. Adding it to EVENT_CLASSES is
    the only registration step. This test exercises that recipe inline."""
    from typing import Literal

    from pydantic import BaseModel

    from vfobs.events.base import Event

    class SyntheticData(BaseModel):
        marker: str

    class TaskSynthetic(Event):
        type: Literal["task.synthetic_for_test"] = "task.synthetic_for_test"
        data: SyntheticData

    instance = TaskSynthetic(
        workgraph_id=WG,
        task_id=TASK,
        source=SRC,
        timestamp=datetime.now(UTC),
        data=SyntheticData(marker="ok"),
    )
    assert instance.type == "task.synthetic_for_test"
    assert instance.data.marker == "ok"
    # JSON Schema export works on the new class without code changes
    schema = TaskSynthetic.model_json_schema()
    assert schema["properties"]["data"]["$ref"].endswith("SyntheticData")
