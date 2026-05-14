from datetime import UTC, datetime
from typing import Any

from vfobs.events.namespaces.anomaly import (
    AnomalyStuckDetected,
    AnomalyStuckDetectedData,
)
from vfobs.events.namespaces.gate import (
    GateFailed,
    GateFailedData,
    GatePassed,
    GatePassedData,
    GateStarted,
    GateStartedData,
)
from vfobs.events.namespaces.harness import (
    HarnessToolCall,
    HarnessToolCallData,
    HarnessTurnCompleted,
    HarnessTurnCompletedData,
    HarnessTurnStarted,
    HarnessTurnStartedData,
)
from vfobs.events.namespaces.judge import (
    JudgeDecision,
    JudgeDecisionData,
    JudgeReviewSubmitted,
    JudgeReviewSubmittedData,
    JudgeStarted,
    JudgeStartedData,
)
from vfobs.events.namespaces.task import (
    ExecutionSummary,
    TaskClaimed,
    TaskClaimedData,
    TaskHeartbeat,
    TaskHeartbeatData,
    TaskStateChanged,
    TaskStateChangedData,
    TaskWorkdirChanged,
    TaskWorkdirChangedData,
)
from vfobs.events.namespaces.workgraph import (
    WorkgraphCompleted,
    WorkgraphCompletedData,
    WorkgraphCreated,
    WorkgraphCreatedData,
    WorkgraphStateChanged,
    WorkgraphStateChangedData,
)


def _now() -> datetime:
    return datetime.now(UTC)


class EventFactory:
    """Single construction surface for every event type.

    Consumers MUST go through these classmethods rather than constructing
    event subclasses directly — keeps the build site uniform and makes
    the v1 schema fingerprint discoverable in one file.
    """

    # ---- workgraph.* ----------------------------------------------------

    @classmethod
    def workgraph_created(
        cls,
        *,
        workgraph_id: str,
        source: str,
        created_by: str,
        kind: str,
        target_repos: list[str],
        timestamp: datetime | None = None,
        **base: Any,
    ) -> WorkgraphCreated:
        return WorkgraphCreated(
            workgraph_id=workgraph_id,
            source=source,
            timestamp=timestamp or _now(),
            data=WorkgraphCreatedData(
                created_by=created_by, kind=kind, target_repos=target_repos
            ),
            **base,
        )

    @classmethod
    def workgraph_state_changed(
        cls,
        *,
        workgraph_id: str,
        source: str,
        from_status: str,
        to_status: str,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> WorkgraphStateChanged:
        return WorkgraphStateChanged(
            workgraph_id=workgraph_id,
            source=source,
            timestamp=timestamp or _now(),
            data=WorkgraphStateChangedData(
                from_status=from_status, to_status=to_status
            ),
            **base,
        )

    @classmethod
    def workgraph_completed(
        cls,
        *,
        workgraph_id: str,
        source: str,
        terminal_status: str,
        task_count: int,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> WorkgraphCompleted:
        return WorkgraphCompleted(
            workgraph_id=workgraph_id,
            source=source,
            timestamp=timestamp or _now(),
            data=WorkgraphCompletedData(
                terminal_status=terminal_status, task_count=task_count
            ),
            **base,
        )

    # ---- task.* ---------------------------------------------------------

    @classmethod
    def task_claimed(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        claimed_by_agent_id: str,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> TaskClaimed:
        return TaskClaimed(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=TaskClaimedData(claimed_by_agent_id=claimed_by_agent_id),
            **base,
        )

    @classmethod
    def task_state_changed(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        from_status: str,
        to_status: str,
        execution_summary: ExecutionSummary | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> TaskStateChanged:
        return TaskStateChanged(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=TaskStateChangedData(
                from_status=from_status,
                to_status=to_status,
                execution_summary=execution_summary,
            ),
            **base,
        )

    @classmethod
    def task_heartbeat(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        at: datetime | None = None,
        current_turn: int | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> TaskHeartbeat:
        now = _now()
        return TaskHeartbeat(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or now,
            data=TaskHeartbeatData(at=at or now, current_turn=current_turn),
            **base,
        )

    @classmethod
    def task_workdir_changed(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        files_changed: int,
        commits: int,
        branch: str | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> TaskWorkdirChanged:
        return TaskWorkdirChanged(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=TaskWorkdirChangedData(
                files_changed=files_changed, commits=commits, branch=branch
            ),
            **base,
        )

    # ---- harness.* ------------------------------------------------------

    @classmethod
    def harness_turn_started(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        turn_number: int,
        model: str,
        prompt_tokens: int | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> HarnessTurnStarted:
        return HarnessTurnStarted(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=HarnessTurnStartedData(
                turn_number=turn_number, model=model, prompt_tokens=prompt_tokens
            ),
            **base,
        )

    @classmethod
    def harness_tool_call(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        turn_number: int,
        tool_name: str,
        tool_args_summary: str | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> HarnessToolCall:
        return HarnessToolCall(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=HarnessToolCallData(
                turn_number=turn_number,
                tool_name=tool_name,
                tool_args_summary=tool_args_summary,
            ),
            **base,
        )

    @classmethod
    def harness_turn_completed(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        turn_number: int,
        completion_tokens: int | None = None,
        duration_ms: int | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> HarnessTurnCompleted:
        return HarnessTurnCompleted(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=HarnessTurnCompletedData(
                turn_number=turn_number,
                completion_tokens=completion_tokens,
                duration_ms=duration_ms,
            ),
            **base,
        )

    # ---- gate.* ---------------------------------------------------------

    @classmethod
    def gate_started(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        gate_name: str,
        command: str,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> GateStarted:
        return GateStarted(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=GateStartedData(gate_name=gate_name, command=command),
            **base,
        )

    @classmethod
    def gate_passed(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        gate_name: str,
        duration_ms: int | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> GatePassed:
        return GatePassed(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=GatePassedData(gate_name=gate_name, duration_ms=duration_ms),
            **base,
        )

    @classmethod
    def gate_failed(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        gate_name: str,
        exit_code: int,
        stderr_tail: str | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> GateFailed:
        return GateFailed(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=GateFailedData(
                gate_name=gate_name, exit_code=exit_code, stderr_tail=stderr_tail
            ),
            **base,
        )

    # ---- judge.* --------------------------------------------------------

    @classmethod
    def judge_started(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        judge_agent_id: str,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> JudgeStarted:
        return JudgeStarted(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=JudgeStartedData(judge_agent_id=judge_agent_id),
            **base,
        )

    @classmethod
    def judge_review_submitted(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        per_ac_verdicts: dict[str, str],
        timestamp: datetime | None = None,
        **base: Any,
    ) -> JudgeReviewSubmitted:
        return JudgeReviewSubmitted(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=JudgeReviewSubmittedData(per_ac_verdicts=per_ac_verdicts),
            **base,
        )

    @classmethod
    def judge_decision(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        decision: str,
        notes: str | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> JudgeDecision:
        return JudgeDecision(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=JudgeDecisionData(decision=decision, notes=notes),  # type: ignore[arg-type]
            **base,
        )

    # ---- anomaly.* ------------------------------------------------------

    @classmethod
    def anomaly_stuck_detected(
        cls,
        *,
        workgraph_id: str,
        task_id: str,
        source: str,
        last_activity_at: datetime,
        t_m_seconds: int,
        last_seen_event_type: str | None = None,
        timestamp: datetime | None = None,
        **base: Any,
    ) -> AnomalyStuckDetected:
        return AnomalyStuckDetected(
            workgraph_id=workgraph_id,
            task_id=task_id,
            source=source,
            timestamp=timestamp or _now(),
            data=AnomalyStuckDetectedData(
                last_activity_at=last_activity_at,
                t_m_seconds=t_m_seconds,
                last_seen_event_type=last_seen_event_type,
            ),
            **base,
        )
