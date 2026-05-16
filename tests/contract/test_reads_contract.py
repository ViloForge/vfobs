import json
from pathlib import Path

import pytest

from vfobs.api.cost import AgentCostResponse, WorkgraphCostResponse
from vfobs.api.dto import (
    EventsFilterResponse,
    TaskEventsResponse,
    TaskReadResponse,
    WorkgraphReadResponse,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "reads_response_shapes.v1.json"
)


def _schemas() -> dict:
    return {
        "WorkgraphReadResponse": WorkgraphReadResponse.model_json_schema(),
        "TaskReadResponse": TaskReadResponse.model_json_schema(),
        "TaskEventsResponse": TaskEventsResponse.model_json_schema(),
        "EventsFilterResponse": EventsFilterResponse.model_json_schema(),
        "WorkgraphCostResponse": WorkgraphCostResponse.model_json_schema(),
        "AgentCostResponse": AgentCostResponse.model_json_schema(),
    }


@pytest.mark.contract
def test_reads_response_shapes_match_v1_fixture():
    """Pinned contract for the WG2 read-API response DTOs. Drift =
    intentional bump; regenerate the fixture in the same commit:
    python -c 'import json; from tests.contract.test_reads_contract import
    _schemas; print(json.dumps(_schemas(), indent=2, sort_keys=True))'
    > tests/fixtures/reads_response_shapes.v1.json"""
    current = _schemas()
    fixture = json.loads(FIXTURE.read_text())
    assert current == fixture, "WG2 read DTO shapes drifted from v1 fixture."
