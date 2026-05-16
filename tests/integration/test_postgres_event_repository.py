import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from vfobs.events import EventFactory
from vfobs.repositories import InMemoryEventRepository, PostgresEventRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic_upgrade(database_url: str):
    env = {
        "VFOBS_DATABASE_URL": database_url,
        "VFOBS_INGEST_TOKEN": "test",
        "VFOBS_APP_DB_PASSWORD": "testapppw",
        "PATH": "/usr/bin:/bin:" + str(REPO_ROOT / ".venv" / "bin"),
    }
    subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "alembic"), "upgrade", "head"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
async def postgres_repo(vfobs_database_url):
    _run_alembic_upgrade(vfobs_database_url)
    engine = create_async_engine(vfobs_database_url)
    yield PostgresEventRepository(engine)
    await engine.dispose()


def _state_changed(workgraph_id="wg_int", task_id="t_int", **kw):
    return EventFactory.task_state_changed(
        workgraph_id=workgraph_id,
        task_id=task_id,
        source="integration",
        from_status="todo",
        to_status="doing",
        timestamp=datetime.now(UTC),
        **kw,
    )


def _heartbeat(workgraph_id="wg_int", task_id="t_int"):
    return EventFactory.task_heartbeat(
        workgraph_id=workgraph_id, task_id=task_id, source="integration",
        timestamp=datetime.now(UTC),
    )


def _tool_call(workgraph_id="wg_int", task_id="t_int", turn=1):
    return EventFactory.harness_tool_call(
        workgraph_id=workgraph_id, task_id=task_id, source="integration",
        turn_number=turn, tool_name="Bash",
        timestamp=datetime.now(UTC),
    )


@pytest.mark.integration
async def test_postgres_store_returns_id_then_get_by_id_round_trips(postgres_repo):
    e = _state_changed()
    eid = await postgres_repo.store(e)
    assert isinstance(eid, int) and eid > 0
    fetched = await postgres_repo.get_by_id(eid)
    assert fetched is not None
    assert fetched.workgraph_id == e.workgraph_id
    assert fetched.task_id == e.task_id
    assert fetched.source == e.source
    assert fetched.type == e.type
    assert fetched.data.from_status == "todo"
    assert fetched.data.to_status == "doing"
    assert fetched.org_id == "viloforge"
    assert fetched.cluster_id == "vafi-dev"


@pytest.mark.integration
async def test_postgres_ids_are_monotonic(postgres_repo):
    e1 = _state_changed()
    e2 = _state_changed()
    id1 = await postgres_repo.store(e1)
    id2 = await postgres_repo.store(e2)
    assert id2 > id1


@pytest.mark.integration
async def test_postgres_get_by_id_missing_returns_none(postgres_repo):
    assert await postgres_repo.get_by_id(99999999) is None


@pytest.mark.integration
async def test_postgres_mixed_event_types_share_sequence(postgres_repo):
    """Events from three different types yield three id ranges from the
    shared BIGSERIAL — proves the single-table design (no per-namespace
    tables) per plan §D1."""
    ids_per_type: dict[str, list[int]] = {"task.state_changed": [], "task.heartbeat": [], "harness.tool_call": []}
    # interleave 17 events across types
    for i in range(17):
        if i % 3 == 0:
            e = _state_changed()
        elif i % 3 == 1:
            e = _heartbeat()
        else:
            e = _tool_call(turn=i)
        eid = await postgres_repo.store(e)
        ids_per_type[e.type].append(eid)
        fetched = await postgres_repo.get_by_id(eid)
        assert fetched is not None
        assert fetched.type == e.type
    # three non-empty buckets prove the mix landed
    assert all(len(v) > 0 for v in ids_per_type.values())
    # collect all ids — should be 17 contiguous (sequence may have been incremented elsewhere; just check monotonic+unique)
    all_ids = sorted(i for ids in ids_per_type.values() for i in ids)
    assert len(all_ids) == 17
    assert len(set(all_ids)) == 17


# ---- Liskov substitution: both repos honor the EventRepository contract -----


@pytest.fixture(params=["inmemory", "postgres"])
async def repo_under_test(request, vfobs_database_url):
    if request.param == "inmemory":
        yield InMemoryEventRepository()
    else:
        _run_alembic_upgrade(vfobs_database_url)
        engine = create_async_engine(vfobs_database_url)
        yield PostgresEventRepository(engine)
        await engine.dispose()


@pytest.mark.integration
async def test_lsp_both_repos_round_trip_an_event(repo_under_test):
    e = _state_changed(workgraph_id="wg_lsp")
    eid = await repo_under_test.store(e)
    assert isinstance(eid, int) and eid > 0
    fetched = await repo_under_test.get_by_id(eid)
    assert fetched is not None
    assert fetched.workgraph_id == "wg_lsp"
    assert fetched.type == "task.state_changed"


@pytest.mark.integration
async def test_lsp_both_repos_return_none_for_missing(repo_under_test):
    assert await repo_under_test.get_by_id(999999999) is None


# ---- WG2-T1 LSP: find_* + cost_summary, one contract, both impls ---------

from vfobs.events.namespaces.task import ExecutionSummary  # noqa: E402


@pytest.mark.integration
async def test_lsp_find_by_workgraph_wraps_storedevent_ordered(repo_under_test):
    i1 = await repo_under_test.store(_state_changed(workgraph_id="wg_f1"))
    await repo_under_test.store(_state_changed(workgraph_id="wg_other"))
    i3 = await repo_under_test.store(_state_changed(workgraph_id="wg_f1"))

    got = await repo_under_test.find_by_workgraph("wg_f1")
    assert [se.id for se in got] == sorted([i1, i3])  # id ASC
    assert all(se.event.workgraph_id == "wg_f1" for se in got)
    assert got[0].model_dump()["id"] == got[0].id  # F1 survives dump


@pytest.mark.integration
async def test_lsp_find_by_task_and_from_id_cursor(repo_under_test):
    ids = [
        await repo_under_test.store(
            _state_changed(workgraph_id="wg_cur", task_id="t_cur")
        )
        for _ in range(4)
    ]
    page = await repo_under_test.find_by_task(
        "t_cur", from_id=ids[1], limit=2
    )
    assert [se.id for se in page] == [ids[1], ids[2]]  # inclusive cursor


@pytest.mark.integration
async def test_lsp_find_filtered_and_combined(repo_under_test):
    hit = await repo_under_test.store(
        _state_changed(workgraph_id="wg_ff", task_id="t_a", agent_id="ag_1")
    )
    await repo_under_test.store(
        _state_changed(workgraph_id="wg_ff", task_id="t_b", agent_id="ag_2")
    )
    got = await repo_under_test.find_filtered(
        workgraph_id="wg_ff", agent_id="ag_1", type_namespace="task"
    )
    assert [se.id for se in got] == [hit]


@pytest.mark.integration
async def test_lsp_cost_summary_dedup_and_scope(repo_under_test):
    with pytest.raises(ValueError):
        await repo_under_test.cost_summary()

    await repo_under_test.store(
        _state_changed(
            workgraph_id="wg_cost", task_id="t_rw",
            execution_summary=ExecutionSummary(
                num_turns=1, total_tokens=10, cost_usd=0.10),
        )
    )
    await repo_under_test.store(
        _state_changed(
            workgraph_id="wg_cost", task_id="t_rw",
            execution_summary=ExecutionSummary(
                num_turns=5, total_tokens=99, cost_usd=0.40),
        )
    )
    # in-flight task with no summary -> excluded
    await repo_under_test.store(
        _state_changed(workgraph_id="wg_cost", task_id="t_inflight")
    )

    cs = await repo_under_test.cost_summary(workgraph_id="wg_cost")
    assert cs.task_count == 1  # F2: reworked t_rw counted once
    assert cs.sample_event_count == 1
    assert cs.total_cost_usd == pytest.approx(0.40)  # latest run wins
    assert cs.total_tokens == 99
    assert cs.total_turns == 5


# ---- WG2-T2 LSP: tail + count helpers, one contract, both impls ---------


@pytest.mark.integration
async def test_lsp_find_last_and_count_helpers(repo_under_test):
    assert await repo_under_test.find_last_by_workgraph("none") is None
    assert await repo_under_test.count_by_workgraph("none") == 0
    assert await repo_under_test.find_last_by_task("none") is None

    await repo_under_test.store(
        _state_changed(workgraph_id="wg_h", task_id="t_h")
    )
    last_id = await repo_under_test.store(
        _state_changed(workgraph_id="wg_h", task_id="t_h")
    )
    await repo_under_test.store(
        _state_changed(workgraph_id="wg_other", task_id="t_o")
    )

    tail = await repo_under_test.find_last_by_workgraph("wg_h")
    assert tail is not None and tail.id == last_id  # highest id wins
    assert tail.event.workgraph_id == "wg_h"
    assert await repo_under_test.count_by_workgraph("wg_h") == 2
    task_tail = await repo_under_test.find_last_by_task("t_h")
    assert task_tail is not None and task_tail.id == last_id
    assert await repo_under_test.count_by_task("t_h") == 2
