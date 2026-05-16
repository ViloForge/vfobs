"""Contract (verifier V17 / D-T0sdk-1): every payload the SDK
emits MUST validate against WG1's LOCKED event_schemas.v1.json.
This is the wire-compat backstop that makes vendoring the models
(instead of importing the server package) safe — vendor drift
fails here, at build, not in production.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from vfobs_sdk.events import (
    ExecutionSummary,
    harness_turn_completed,
    harness_turn_started,
    task_claimed,
    task_heartbeat,
    task_state_changed,
)

_FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "event_schemas.v1.json"
)
SCHEMAS = json.loads(_FIXTURE.read_text())


def _events():
    k = dict(workgraph_id="wg", task_id="t", source="sdk")
    return [
        task_claimed(claimed_by_agent_id="ag-1", **k),
        task_heartbeat(current_turn=4, **k),
        task_state_changed(
            from_status="doing", to_status="done",
            execution_summary=ExecutionSummary(
                num_turns=3, total_tokens=99, cost_usd=0.4
            ),
            **k,
        ),
        harness_turn_started(turn_number=1, model="claude-x", **k),
        harness_turn_completed(
            turn_number=1, completion_tokens=50, duration_ms=1200, **k
        ),
    ]


@pytest.mark.contract
@pytest.mark.parametrize("ev", _events(), ids=lambda e: e.type)
def test_emitted_payload_validates_against_wg1_locked_schema(ev):
    schema = SCHEMAS[ev.type]
    payload = json.loads(ev.model_dump_json())
    jsonschema.validate(  # raises on any drift from the WG1 contract
        instance=payload,
        schema=schema,
        cls=jsonschema.Draft202012Validator,
    )


@pytest.mark.contract
def test_sdk_covers_only_known_locked_types():
    for ev in _events():
        assert ev.type in SCHEMAS  # no event type the server can't ingest
