"""Crash-resilient host execution for the Jeeves 100-milestone work queue.

A work cycle is explicitly called by the host. It never starts threads, calls
remote models, or manufactures quality measurements. Every attempted check
requires two host-provided reviewers and a source-bound durable queue.

The lease is checkpointed *before* a host checker executes. A crash or checker
exception leaves that lease recorded; later cycles only recover it through
its bounded expiry path. Every verified settlement is durably committed before
the cycle advances or its result is reported as accepted.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Mapping

from .delivery_milestone_queue import MilestoneQueue, QueueContractError
from .delivery_milestone_store import (
    MilestoneCheckpointError, SQLiteMilestoneQueueStore,
)
from .delivery_milestone_workbench import (
    ExecutionVerdict, HostChecker,
)
from .types import stable_fingerprint

_WORKER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class WorkCycleError(ValueError):
    """A host execution cycle is unconfigured, invalid or unsafe."""


class _HostReviewerError(WorkCycleError):
    """A reviewer failed after the durable work lease was acquired."""


@dataclass(frozen=True, slots=True)
class WorkCyclePolicy:
    max_claims: int = 10
    max_wall_seconds: float = 600.0
    retry_seconds: float = 30.0
    recover_expired: bool = True

    def __post_init__(self) -> None:
        if type(self.max_claims) is not int or not 1 <= self.max_claims <= 100:
            raise WorkCycleError("work cycle claim budget must be 1..100")
        if (type(self.max_wall_seconds) not in (int, float)
                or not math.isfinite(self.max_wall_seconds)
                or not 1 <= self.max_wall_seconds <= 3600):
            raise WorkCycleError("work cycle duration must be finite 1..3600")
        if (type(self.retry_seconds) not in (int, float)
                or not math.isfinite(self.retry_seconds)
                or not 0 <= self.retry_seconds <= 86400):
            raise WorkCycleError("invalid host retry interval")
        if type(self.recover_expired) is not bool:
            raise WorkCycleError("recover_expired must be a boolean")


@dataclass(frozen=True, slots=True)
class WorkCycleResult:
    run_id: str
    source_commit: str
    artifact_digest: str
    status: str
    attempted: int
    passed: int
    blocked: int
    candidate_completed: int
    active_leases: int
    deferred: int
    source_queue_digest: str
    final_queue_digest: str
    generation: int
    generation_receipt: str
    verdict_digests: tuple[str, ...]
    error_type: str | None = None

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "run": self.run_id, "source": self.source_commit,
            "artifact": self.artifact_digest, "status": self.status,
            "attempted": self.attempted, "passed": self.passed,
            "blocked": self.blocked, "candidate_completed": self.candidate_completed,
            "active_leases": self.active_leases, "deferred": self.deferred,
            "before": self.source_queue_digest, "after": self.final_queue_digest,
            "generation": self.generation, "generation_receipt": self.generation_receipt,
            "verdicts": self.verdict_digests, "error": self.error_type,
        })

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "source_commit": self.source_commit,
            "candidate_completed": self.candidate_completed,
            "attempted": self.attempted,
            "passed": self.passed,
            "blocked": self.blocked,
            "active_leases": self.active_leases,
            "deferred": self.deferred,
            "checkpoint_generation": self.generation,
            "checkpoint_receipt": self.generation_receipt,
            "cycle_receipt": self.fingerprint,
            # Objective acceptance is not production qualification.
            "independent_production_signoff": False,
            "production_qualified_milestones": 0,
        }


Clock = Callable[[], float]
StopCheck = Callable[[], bool]


def _now(clock: Clock) -> float:
    instant = clock()
    if type(instant) not in (int, float) or not math.isfinite(instant) or instant < 0:
        raise WorkCycleError("host clock must return a finite nonnegative number")
    return float(instant)


def _reviewer(checker: HostChecker) -> HostChecker:
    def guarded(spec, source, artifact):
        try:
            return checker(spec, source, artifact)
        except Exception as exc:
            # Avoid emitting user data, host stacktraces or source in receipts.
            raise _HostReviewerError(type(exc).__name__) from exc
    return guarded


def execute_durable_work_cycle(
    store: SQLiteMilestoneQueueStore,
    run_id: str,
    *,
    source_commit: str,
    artifact_digest: str,
    owner: str,
    clock: Clock,
    checkers: Mapping[str, tuple[HostChecker | None, HostChecker | None]],
    policy: WorkCyclePolicy | None = None,
    stop_requested: StopCheck | None = None,
) -> WorkCycleResult:
    """Run bounded, actual host measurements from an existing durable queue.

    Host must explicitly initialize a queue before calling this method.
    A missing host checker is left untouched; its metric is not recorded as
    passing. Duplicate concurrent callers are rejected by SQLite's CAS.
    """
    if not isinstance(store, SQLiteMilestoneQueueStore):
        raise WorkCycleError("work cycle needs an explicit durable checkpoint store")
    if not isinstance(owner, str) or not _WORKER.fullmatch(owner):
        raise WorkCycleError("work cycle needs a bounded owner identity")
    if not callable(clock):
        raise WorkCycleError("work cycle clock must be a host callback")
    if stop_requested is not None and not callable(stop_requested):
        raise WorkCycleError("stop callback is invalid")
    if not isinstance(checkers, Mapping):
        raise WorkCycleError("reviewer registry must be a mapping")
    for pair in checkers.values():
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise WorkCycleError("every reviewer registration requires two checkers")
    limit = policy or WorkCyclePolicy()
    if not isinstance(limit, WorkCyclePolicy):
        raise WorkCycleError("work cycle policy is invalid")
    # Read first; no implicit database writes or queuing for missing runs.
    saved = store.load(
        run_id, source_commit=source_commit, artifact_digest=artifact_digest,
    )
    if saved is None:
        raise WorkCycleError("source-bound milestone queue has not been initialized")
    queue = saved.queue
    initial_digest = queue.fingerprint
    beginning = _now(clock)
    last_clock = beginning
    initial_control = store.operator_control(
        run_id, source_commit=source_commit, artifact_digest=artifact_digest,
    )
    if initial_control is not None and initial_control.mode != "running":
        history = store.checkpoint_history(run_id)
        return WorkCycleResult(
            run_id, source_commit, artifact_digest,
            "operator_paused" if initial_control.mode == "paused" else "operator_cancelled",
            0, 0, 0, queue.board.completion_count,
            sum(item.status == "leased" for item in queue.work),
            sum(item.status == "pending" for item in queue.work),
            initial_digest, queue.fingerprint, saved.generation,
            history[-1]["receipt_digest"], (),
        )

    def observe_time() -> float:
        nonlocal last_clock
        current = _now(clock)
        if current < last_clock:
            raise WorkCycleError("work cycle clock moved backward")
        last_clock = current
        return current

    if limit.recover_expired:
        recovered = queue.expire(beginning, retry_seconds=limit.retry_seconds)
        if recovered.fingerprint != queue.fingerprint:
            saved = store.save(
                run_id, recovered, expected_fingerprint=queue.fingerprint,
            )
            queue = saved.queue

    attempted = passed = blocked = 0
    verdicts: list[str] = []
    status = "budget_exhausted"
    error_type: str | None = None
    for _ in range(limit.max_claims):
        now = observe_time()
        if now - beginning >= limit.max_wall_seconds:
            status = "time_budget_exhausted"
            break
        control = store.operator_control(
            run_id, source_commit=source_commit, artifact_digest=artifact_digest,
        )
        if control is not None and control.mode != "running":
            status = "operator_paused" if control.mode == "paused" else "operator_cancelled"
            break
        if stop_requested is not None:
            decision = stop_requested()
            if type(decision) is not bool:
                raise WorkCycleError("stop callback must return a boolean")
            if decision:
                status = "operator_paused"
                break
        ready = queue.ready(now)
        if not ready:
            status = "complete" if queue.board.completion_count == 100 else "no_ready_work"
            break
        milestone_id = ready[0]
        primary, independent = checkers.get(milestone_id, (None, None))
        if (not callable(primary) or not callable(independent)
                or primary is independent):
            status = "missing_independent_host_reviewers"
            break
        acquired, lease = queue.claim(owner, now)
        if lease is None or lease.milestone_id != milestone_id:
            raise WorkCycleError("queue claim differs from source-bound ready selection")
        # Claim is durably committed before any external code is executed.
        saved = store.save(
            run_id, acquired, expected_fingerprint=queue.fingerprint,
        )
        queue = saved.queue
        def lease_bound(checker: HostChecker) -> HostChecker:
            verified = _reviewer(checker)

            def inspect(spec, source, artifact):
                before = observe_time()
                if before >= lease.expires_at:
                    raise _HostReviewerError("review_lease_expired")
                if before - beginning >= limit.max_wall_seconds:
                    raise _HostReviewerError("cycle_time_budget_exceeded")
                result = verified(spec, source, artifact)
                after = observe_time()
                if after >= lease.expires_at:
                    raise _HostReviewerError("review_lease_expired")
                if after - beginning >= limit.max_wall_seconds:
                    raise _HostReviewerError("cycle_time_budget_exceeded")
                return result
            return inspect

        try:
            settled, verdict = queue.settle(
                lease, observe_time(),
                lease_bound(primary), lease_bound(independent),
                retry_seconds=limit.retry_seconds,
            )
        except _HostReviewerError as exc:
            status = "host_reviewer_failed"
            error_type = str(exc)
            # Remain leased. A later recovery cycle revokes the expired lease.
            break
        except QueueContractError:
            # A reviewer may have run past lease expiry. Fail closed; the
            # claimed lease persists and is only revoked by explicit expiry.
            status = "lease_expired_during_review"
            break
        except (ValueError, TypeError, AttributeError) as exc:
            # Malformed host evidence is not an acceptance result.
            status = "invalid_host_review"
            error_type = type(exc).__name__
            break
        # Cancellation after the host measurement but before settlement must
        # never admit the result. The transaction also checks the same control
        # row, closing the read-to-write cancellation race.
        control = store.operator_control(
            run_id, source_commit=source_commit, artifact_digest=artifact_digest,
        )
        if control is not None and control.mode == "cancelled":
            status = "operator_cancelled"
            break
        try:
            saved = store.save(
                run_id, settled, expected_fingerprint=queue.fingerprint,
            )
        except MilestoneCheckpointError:
            control = store.operator_control(
                run_id, source_commit=source_commit, artifact_digest=artifact_digest,
            )
            if control is not None and control.mode == "cancelled":
                status = "operator_cancelled"
                break
            raise
        queue = saved.queue
        attempted += 1
        passed += int(verdict.passed)
        blocked += int(not verdict.passed)
        verdicts.append(verdict.fingerprint)
        if queue.board.completion_count == 100:
            status = "complete"
            break
    history = store.checkpoint_history(run_id)
    if not history:
        raise WorkCycleError("durable host checkpoint lacks generation history")
    return WorkCycleResult(
        run_id, source_commit, artifact_digest, status, attempted,
        passed, blocked, queue.board.completion_count,
        sum(item.status == "leased" for item in queue.work),
        sum(item.status == "pending" for item in queue.work),
        initial_digest, queue.fingerprint, saved.generation,
        history[-1]["receipt_digest"], tuple(verdicts), error_type,
    )
