"""vfobs-sdk-python — the public client contract for vfobs (NFR5).

The HTTP shape is an implementation detail of this SDK. Consumers
(vafi controller, watcher, retro tooling) bind to this package,
never to raw vfobs HTTP.
"""

__version__ = "0.1.0"

from vfobs_sdk.emitter import (
    BufferingEmitter,
    Emitter,
    HttpEmitter,
    NullEmitter,
    make_emitter,
)
from vfobs_sdk.events import (
    Event,
    task_claimed,
    task_heartbeat,
    task_state_changed,
    task_workdir_changed,
    harness_turn_started,
    harness_turn_completed,
    ExecutionSummary,
)

__all__ = [
    "__version__",
    "Emitter",
    "HttpEmitter",
    "NullEmitter",
    "BufferingEmitter",
    "make_emitter",
    "Event",
    "task_claimed",
    "task_heartbeat",
    "task_state_changed",
    "task_workdir_changed",
    "harness_turn_started",
    "harness_turn_completed",
    "ExecutionSummary",
]
