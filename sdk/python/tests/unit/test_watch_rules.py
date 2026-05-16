from datetime import UTC, datetime, timedelta

import pytest

from vfobs_sdk.watch import (
    ApproachingTimeout,
    Crashed,
    Stall,
    WatchState,
    default_rules,
    evaluate,
)

NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)


def _st(*, claimed=None, hb=None, workdir=None, terminal=False, timeout=1800):
    """workdir= : seconds since the last task.workdir_changed (the
    progress signal, corrected per pre-impl-review G2)."""
    return WatchState(
        now=NOW,
        claimed_at=NOW - timedelta(seconds=claimed) if claimed else None,
        last_heartbeat_at=NOW - timedelta(seconds=hb) if hb else None,
        last_workdir_change_at=(
            NOW - timedelta(seconds=workdir) if workdir else None
        ),
        terminal=terminal,
        task_timeout_s=timeout,
    )


@pytest.mark.unit
def test_stall_is_pi_hang_alive_but_no_workdir_progress():
    # heartbeat fresh (5s ago) but workdir untouched for 300s
    s = _st(claimed=600, hb=5, workdir=300)
    v = Stall(stall_s=60, crash_s=120).evaluate(s)
    assert v is not None and v.level == "STALLED"


@pytest.mark.unit
def test_stall_never_fired_when_workdir_progressing_even_with_no_harness():
    """The exact FALSE POSITIVE the merged (pre-G2) rule had: a
    healthy long task emits NO harness events mid-run (opaque
    subprocess) but DOES change its workdir. Must be OK, not
    STALLED."""
    s = _st(claimed=1800, hb=5, workdir=8)  # workdir touched 8s ago
    assert Stall(60, 120).evaluate(s) is None


@pytest.mark.unit
def test_stall_from_claim_when_no_workdir_change_yet():
    # never touched workdir; 300s since claim => stalled
    s = _st(claimed=300, hb=5, workdir=None)
    assert Stall(60, 120).evaluate(s).level == "STALLED"


@pytest.mark.unit
def test_stall_defers_to_crashed_when_heartbeat_gap_large():
    s = _st(claimed=600, hb=300, workdir=300)  # hb 300s > crash 120
    assert Stall(60, 120).evaluate(s) is None  # Crashed's call


@pytest.mark.unit
def test_crashed_fires_on_heartbeat_gap():
    v = Crashed(120).evaluate(_st(claimed=600, hb=300))
    assert v is not None and v.level == "CRASHED"


@pytest.mark.unit
def test_approaching_timeout_boundary_079_vs_081():
    r = ApproachingTimeout(0.8)
    assert r.evaluate(_st(claimed=int(0.79 * 1000), timeout=1000)) is None
    v = r.evaluate(_st(claimed=int(0.81 * 1000), timeout=1000))
    assert v is not None and v.level == "APPROACHING_TIMEOUT"


@pytest.mark.unit
def test_no_rule_fires_when_terminal():
    s = _st(claimed=99999, hb=99999, terminal=True)
    assert evaluate(
        s, default_rules(stall_s=60, crash_s=120, fraction=0.8)
    ).level == "OK"


@pytest.mark.unit
def test_priority_crashed_before_stall_before_approaching():
    rules = default_rules(stall_s=60, crash_s=120, fraction=0.8)
    s = _st(claimed=9999, hb=9999, timeout=100)  # crashed AND past timeout
    assert evaluate(s, rules).level == "CRASHED"


@pytest.mark.unit
def test_ok_when_healthy_and_workdir_progressing():
    rules = default_rules(stall_s=60, crash_s=120, fraction=0.8)
    s = _st(claimed=100, hb=3, workdir=4, timeout=1800)
    assert evaluate(s, rules).level == "OK"
