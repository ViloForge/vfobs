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
