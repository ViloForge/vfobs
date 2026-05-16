"""vfobs-watch — live proactive stuck-detection.

Turns the WG2 read API into a "this run is stuck, intervene now"
verdict instead of waiting for the task timeout (DESIGN §3 pi-hang
failure). The AnomalyRule objects are PURE functions of WatchState
— WG4 reuses these exact classes server-side; the watcher is
their first consumer, not a throwaway.
"""

from __future__ import annotations

import argparse
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

from vfobs_sdk.read_client import ReadClient, ReadUnavailable, StoredEventView

_TERMINAL = {"done", "failed", "cancelled", "rejected"}


def _parse_ts(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


@dataclass(frozen=True)
class WatchState:
    now: datetime
    claimed_at: datetime | None
    last_heartbeat_at: datetime | None
    # Progress signal (corrected per pre-impl-review G2): the
    # harness is an opaque buffered subprocess — it emits no
    # mid-run events, so harness recency CANNOT mean "progressing".
    # The DESIGN's actual stuck criterion is "workdir has not
    # changed in N minutes" → progress = task.workdir_changed.
    last_workdir_change_at: datetime | None
    terminal: bool
    task_timeout_s: float

    @classmethod
    def from_events(
        cls, events: list[StoredEventView], *, now: datetime,
        task_timeout_s: float,
    ) -> "WatchState":
        claimed_at = hb = workdir_at = None
        terminal = False
        for e in events:
            ts = _parse_ts(e.timestamp)
            if e.type == "task.claimed":
                claimed_at = ts if claimed_at is None else claimed_at
            elif e.type == "task.heartbeat":
                hb = ts if hb is None or ts > hb else hb
            elif e.type == "task.workdir_changed":
                if workdir_at is None or ts > workdir_at:
                    workdir_at = ts
            elif e.type == "task.state_changed":
                if e.data.get("to_status") in _TERMINAL:
                    terminal = True
        return cls(
            now=now, claimed_at=claimed_at, last_heartbeat_at=hb,
            last_workdir_change_at=workdir_at,
            terminal=terminal, task_timeout_s=task_timeout_s,
        )


@dataclass(frozen=True)
class Verdict:
    level: str  # OK | APPROACHING_TIMEOUT | STALLED | CRASHED
    reason: str

    @property
    def is_alert(self) -> bool:
        return self.level != "OK"


class AnomalyRule(ABC):
    @abstractmethod
    def evaluate(self, s: WatchState) -> Verdict | None: ...


class Crashed(AnomalyRule):
    def __init__(self, crash_s: float = 120.0) -> None:
        self._crash = crash_s

    def evaluate(self, s: WatchState) -> Verdict | None:
        if s.terminal or s.last_heartbeat_at is None:
            return None
        age = (s.now - s.last_heartbeat_at).total_seconds()
        if age > self._crash:
            return Verdict("CRASHED", f"no heartbeat for {age:.0f}s")
        return None


class Stall(AnomalyRule):
    """The exact pi-hang signal: alive (heartbeats fresh) but no
    workdir progress for too long. (Input corrected per pre-impl-
    review G2 — was harness recency, which is unobservable mid-run
    because the harness is an opaque buffered subprocess.)"""

    def __init__(self, stall_s: float = 60.0, crash_s: float = 120.0) -> None:
        self._stall = stall_s
        self._crash = crash_s

    def evaluate(self, s: WatchState) -> Verdict | None:
        if s.terminal or s.last_heartbeat_at is None:
            return None
        hb_age = (s.now - s.last_heartbeat_at).total_seconds()
        if hb_age > self._crash:
            return None  # that's Crashed's call, not Stall's
        # progress = workdir change; before any workdir change,
        # measure from claim (a task that never touches its workdir
        # within stall_s IS the pi-hang).
        progressed_at = s.last_workdir_change_at or s.claimed_at
        if progressed_at is None:
            return None
        prog_age = (s.now - progressed_at).total_seconds()
        if prog_age > self._stall:
            return Verdict(
                "STALLED",
                f"alive (hb {hb_age:.0f}s) but no workdir progress "
                f"for {prog_age:.0f}s",
            )
        return None


class ApproachingTimeout(AnomalyRule):
    def __init__(self, fraction: float = 0.8) -> None:
        self._frac = fraction

    def evaluate(self, s: WatchState) -> Verdict | None:
        if s.terminal or s.claimed_at is None or s.task_timeout_s <= 0:
            return None
        elapsed = (s.now - s.claimed_at).total_seconds()
        if elapsed > self._frac * s.task_timeout_s:
            return Verdict(
                "APPROACHING_TIMEOUT",
                f"elapsed {elapsed:.0f}s > {self._frac:.0%} of "
                f"{s.task_timeout_s:.0f}s timeout",
            )
        return None


def evaluate(state: WatchState, rules: list[AnomalyRule]) -> Verdict:
    for rule in rules:  # priority order: Crashed > Stall > Approaching
        v = rule.evaluate(state)
        if v is not None:
            return v
    return Verdict("OK", "progressing" if not state.terminal else "terminal")


def default_rules(
    *, stall_s: float, crash_s: float, fraction: float
) -> list[AnomalyRule]:
    return [
        Crashed(crash_s),
        Stall(stall_s, crash_s),
        ApproachingTimeout(fraction),
    ]


def _watch_once(client: ReadClient, task_id: str, rules, timeout_s) -> Verdict:
    try:
        events = client.task_events(task_id)
    except ReadUnavailable as exc:
        return Verdict("OK", f"watch unavailable this tick: {exc}")
    state = WatchState.from_events(
        events, now=datetime.now(UTC), task_timeout_s=timeout_s
    )
    return evaluate(state, rules)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vfobs-watch")
    p.add_argument("--task", required=True)
    p.add_argument("--workgraph", default=None)
    p.add_argument("--url", default="http://localhost:18080")
    p.add_argument("--token", default="watch")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--task-timeout", type=float, default=1800.0)
    p.add_argument("--stall-seconds", type=float, default=60.0)
    p.add_argument("--crash-seconds", type=float, default=120.0)
    p.add_argument("--fraction", type=float, default=0.8)
    p.add_argument("--once", action="store_true", help="single evaluation")
    a = p.parse_args(argv)

    rules = default_rules(
        stall_s=a.stall_seconds, crash_s=a.crash_seconds,
        fraction=a.fraction,
    )
    client = ReadClient(a.url, a.token)
    try:
        while True:
            v = _watch_once(client, a.task, rules, a.task_timeout)
            print(f"[{datetime.now(UTC).isoformat()}] {v.level}: {v.reason}")
            if v.is_alert:
                print(f"ALERT: {v.level} — {v.reason}", file=sys.stderr)
                return 2
            if v.reason == "terminal" or a.once:
                return 0
            time.sleep(a.interval)
    finally:
        client.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
