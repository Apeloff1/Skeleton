"""Explicit bounded Prood worker dispatch through a durable work journal.

No worker pool is started implicitly. Each dispatch is authorized against live
resource policy before claim. The result owner must durably persist evidence
before reporting success; incomplete execution remains claimed/uncertain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from skeleton.frontier.durable_work import DurableWorkJournal, WorkClaim, WorkStatus, WorkConflict


@dataclass(frozen=True, slots=True)
class WorkerOutcome:
    work_id: str
    succeeded: bool
    receipt_digest: str


class WorkerExecutor(Protocol):
    async def execute_and_commit(self, claim: WorkClaim) -> WorkerOutcome:
        """Return only after the result is durably committed."""


class WorkerAdmission(Protocol):
    def allow(self, work: WorkStatus) -> bool:
        """Evaluate live resource and capability policy."""


@dataclass(frozen=True, slots=True)
class DispatchReport:
    considered: int
    claimed: int
    completed: tuple[WorkStatus, ...]
    uncertain: tuple[str, ...]
    denied: tuple[str, ...]


class ProodSupervisor:
    """One caller-owned dispatch loop; no autonomous retry or background work."""

    def __init__(self, journal: DurableWorkJournal, admission: WorkerAdmission,
                 executor: WorkerExecutor, *, owner: str):
        if type(journal) is not DurableWorkJournal:
            raise TypeError("canonical work journal required")
        if not callable(getattr(admission, "allow", None)):
            raise TypeError("explicit live admission policy required")
        if not callable(getattr(executor, "execute_and_commit", None)):
            raise TypeError("durable worker executor required")
        if type(owner) is not str or not owner.strip() or len(owner) > 128:
            raise ValueError("worker supervisor identity required")
        self._journal = journal
        self._admission = admission
        self._executor = executor
        self._owner = owner
        self._dispatching = False

    async def dispatch(self, *, limit: int = 16) -> DispatchReport:
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("bounded dispatch limit required")
        if self._dispatching:
            raise RuntimeError("supervisor dispatch already active")
        self._dispatching = True
        claimed = 0
        completed = []
        uncertain = []
        denied = []
        try:
            candidates = self._journal.ready(kind="prood.worker", limit=limit)
            for work in candidates:
                # An adapter can refuse unsupported input before the irreversible
                # claim. The admission policy remains an independent requirement.
                accepts = getattr(self._executor, "accepts", None)
                if callable(accepts):
                    try:
                        if accepts(work.work_id) is not True:
                            denied.append(work.work_id)
                            continue
                    except (KeyError, WorkConflict):
                        denied.append(work.work_id)
                        continue
                if self._admission.allow(work) is not True:
                    denied.append(work.work_id)
                    continue
                try:
                    claim = self._journal.claim(work.work_id, owner=self._owner)
                except (KeyError, WorkConflict):
                    # Another owner may have claimed or cancelled the snapshot.
                    denied.append(work.work_id)
                    continue
                claimed += 1
                try:
                    outcome = await self._executor.execute_and_commit(claim)
                    if (type(outcome) is not WorkerOutcome or outcome.work_id != claim.work_id
                            or type(outcome.succeeded) is not bool):
                        raise ValueError("worker outcome does not bind claimed order")
                    completed.append(self._journal.finish(
                        claim, succeeded=outcome.succeeded, receipt_digest=outcome.receipt_digest
                    ))
                except Exception:
                    # Execution may have committed despite the error. Preserve
                    # the durable claimed record; independent reconciliation is
                    # the only path to terminal state without the original claim.
                    uncertain.append(claim.work_id)
                    break
            return DispatchReport(len(candidates), claimed, tuple(completed),
                                  tuple(uncertain), tuple(denied))
        finally:
            self._dispatching = False
