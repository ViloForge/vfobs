from datetime import UTC, datetime

import pytest

from vfobs.events import EventFactory
from vfobs.repositories import EventRepository, InMemoryEventRepository


def _event(workgraph_id: str = "wg_unit", from_status: str = "todo", to_status: str = "doing"):
    return EventFactory.task_state_changed(
        workgraph_id=workgraph_id,
        task_id="t_unit",
        source="unit",
        from_status=from_status,
        to_status=to_status,
        timestamp=datetime.now(UTC),
    )


@pytest.mark.unit
async def test_inmemory_store_returns_monotonic_ids():
    repo = InMemoryEventRepository()
    e1 = _event()
    e2 = _event()
    e3 = _event()
    assert await repo.store(e1) == 1
    assert await repo.store(e2) == 2
    assert await repo.store(e3) == 3


@pytest.mark.unit
async def test_inmemory_get_by_id_round_trips():
    repo = InMemoryEventRepository()
    e = _event()
    eid = await repo.store(e)
    fetched = await repo.get_by_id(eid)
    assert fetched == e


@pytest.mark.unit
async def test_inmemory_get_by_id_missing_returns_none():
    repo = InMemoryEventRepository()
    assert await repo.get_by_id(9999) is None


@pytest.mark.unit
def test_abstract_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        EventRepository()  # type: ignore[abstract]


# ---- WG2-T1: read methods + F1 (Event.id) + F2 (cost de-dup) --------------

from vfobs.events.namespaces.task import ExecutionSummary  # noqa: E402
from vfobs.repositories import CostSummary  # noqa: E402


def _sc(wg, task, *, agent_id=None, es=None, to="done"):
    return EventFactory.task_state_changed(
        workgraph_id=wg, task_id=task, source="unit",
        from_status="doing", to_status=to, execution_summary=es,
        timestamp=datetime.now(UTC),
        **({"agent_id": agent_id} if agent_id else {}),
    )


@pytest.mark.unit
async def test_get_by_id_stays_id_free_d_t1_1():
    """D-T1-1 regression guard: get_by_id behavior unchanged — returns
    a bare Event equal to the stored one; Event carries no id (R2 —
    the locked ingest schema is untouched)."""
    repo = InMemoryEventRepository()
    e = _event()
    eid = await repo.store(e)
    fetched = await repo.get_by_id(eid)
    assert fetched == e
    assert not hasattr(fetched, "id")  # R2: id is not on Event


@pytest.mark.unit
async def test_find_by_workgraph_orders_and_wraps_storedevent_f1():
    repo = InMemoryEventRepository()
    i1 = await repo.store(_event(workgraph_id="wg_a"))
    await repo.store(_event(workgraph_id="wg_b"))
    i3 = await repo.store(_event(workgraph_id="wg_a"))

    got = await repo.find_by_workgraph("wg_a")
    assert [se.id for se in got] == [i1, i3]  # F1/R2: id on StoredEvent, ASC
    assert got[0].event.workgraph_id == "wg_a"
    # F1 regression guard (WG1-F1 silent-drop class): id survives dump
    dumped = got[0].model_dump()
    assert dumped["id"] == i1
    assert dumped["event"]["workgraph_id"] == "wg_a"


@pytest.mark.unit
async def test_find_by_workgraph_from_id_cursor_and_limit():
    repo = InMemoryEventRepository()
    ids = [await repo.store(_event(workgraph_id="wg_c")) for _ in range(5)]
    page = await repo.find_by_workgraph("wg_c", from_id=ids[2], limit=2)
    assert [se.id for se in page] == [ids[2], ids[3]]  # inclusive cursor


@pytest.mark.unit
async def test_find_by_task_filters():
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg", "t_1"))
    keep = await repo.store(_sc("wg", "t_2"))
    got = await repo.find_by_task("t_2")
    assert [se.id for se in got] == [keep]


@pytest.mark.unit
async def test_find_filtered_and_combines_and_namespace():
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg_x", "t_1", agent_id="ag_1"))
    hit = await repo.store(_sc("wg_x", "t_2", agent_id="ag_2"))
    await repo.store(_sc("wg_y", "t_3", agent_id="ag_2"))

    got = await repo.find_filtered(workgraph_id="wg_x", agent_id="ag_2")
    assert [se.id for se in got] == [hit]

    ns = await repo.find_filtered(type_namespace="task")
    assert len(ns) == 3  # all task.state_changed
    assert await repo.find_filtered(type_namespace="harness") == []


@pytest.mark.unit
async def test_find_filtered_limit_hard_capped_at_1000():
    repo = InMemoryEventRepository()
    for _ in range(3):
        await repo.store(_event(workgraph_id="wg_cap"))
    got = await repo.find_filtered(workgraph_id="wg_cap", limit=10_000)
    assert len(got) == 3  # clamp doesn't error; just bounds the page


@pytest.mark.unit
async def test_cost_summary_requires_exactly_one_scope():
    repo = InMemoryEventRepository()
    with pytest.raises(ValueError):
        await repo.cost_summary()
    with pytest.raises(ValueError):
        await repo.cost_summary(workgraph_id="w", agent_id="a")


@pytest.mark.unit
async def test_cost_summary_empty_is_zeros():
    repo = InMemoryEventRepository()
    cs = await repo.cost_summary(workgraph_id="none")
    assert cs == CostSummary(
        total_cost_usd=0.0, total_tokens=0, total_turns=0,
        task_count=0, sample_event_count=0,
    )


@pytest.mark.unit
async def test_cost_summary_sums_and_excludes_inflight_and_handles_missing_fields():
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg_k", "t_1", es=ExecutionSummary(
        num_turns=3, total_tokens=100, cost_usd=0.5)))
    # missing inner fields contribute 0, not NaN/error:
    await repo.store(_sc("wg_k", "t_2", es=ExecutionSummary(cost_usd=0.25)))
    # in-flight task: no execution_summary -> excluded entirely:
    await repo.store(_sc("wg_k", "t_3", to="doing", es=None))

    cs = await repo.cost_summary(workgraph_id="wg_k")
    assert cs.total_cost_usd == pytest.approx(0.75)
    assert cs.total_tokens == 100
    assert cs.total_turns == 3
    assert cs.task_count == 2  # t_1 + t_2; t_3 excluded
    assert cs.sample_event_count == 2


@pytest.mark.unit
async def test_cost_summary_dedup_reworked_task_counted_once_f2():
    """F2: a task with two summary-bearing state_changed events
    (rework) is counted ONCE — the later (higher-id) wins, no
    double-count."""
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg_r", "t_rw", es=ExecutionSummary(
        num_turns=1, total_tokens=10, cost_usd=0.10)))   # first run
    await repo.store(_sc("wg_r", "t_rw", es=ExecutionSummary(
        num_turns=4, total_tokens=99, cost_usd=0.40)))   # rework run

    cs = await repo.cost_summary(workgraph_id="wg_r")
    assert cs.task_count == 1
    assert cs.sample_event_count == 1
    assert cs.total_cost_usd == pytest.approx(0.40)  # latest, not 0.50
    assert cs.total_tokens == 99
    assert cs.total_turns == 4


@pytest.mark.unit
async def test_cost_summary_by_agent_scope():
    repo = InMemoryEventRepository()
    await repo.store(_sc("wg", "t_1", agent_id="ag_x",
                         es=ExecutionSummary(cost_usd=1.0)))
    await repo.store(_sc("wg", "t_2", agent_id="ag_y",
                         es=ExecutionSummary(cost_usd=2.0)))
    cs = await repo.cost_summary(agent_id="ag_x")
    assert cs.total_cost_usd == pytest.approx(1.0)
    assert cs.task_count == 1
