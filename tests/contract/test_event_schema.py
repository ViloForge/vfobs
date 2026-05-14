import json
from pathlib import Path

import pytest

from vfobs.events.schema import dump_event_schemas

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "event_schemas.v1.json"
)


@pytest.mark.contract
def test_event_schemas_match_v1_fixture():
    """Pinned contract: dump_event_schemas() must equal the committed v1
    fixture. Any drift = intentional schema bump (and the fixture is
    updated alongside, in the same commit)."""
    current = dump_event_schemas()
    fixture = json.loads(FIXTURE.read_text())
    assert current == fixture, (
        "Event schemas drifted from v1 fixture. If the change is intentional, "
        "regenerate the fixture: python -c 'import json; from vfobs.events.schema import "
        "dump_event_schemas; print(json.dumps(dump_event_schemas(), indent=2, sort_keys=True))' "
        f"> {FIXTURE}"
    )
