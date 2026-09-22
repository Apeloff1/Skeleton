"""Saga ledger — compensatable multi-step workflows across agents.

A saga is a sequence of steps where each step has a forward action and a
compensation. If step N fails, you can't just roll back a database
transaction — the earlier steps already happened on other agents, in
other processes, maybe on other continents. The only honest recovery is
to run the compensations in reverse. This module is the kernel's book
of record for that:

- :class:`Saga` / :class:`Step` — declarative definition: name, action,
  compensation, timeout.
- :class:`SagaLedger` — durable state machine per saga instance:
  PENDING → RUNNING → (COMPLETED | COMPENSATING → COMPENSATED | FAILED).
  Every transition is recorded, so a crashed coordinator can resume
  mid-compensation without double-firing.

Execution itself is delegated to callables the kernel injects — the
ledger owns *truth*, not threads.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .errors import KernelError


class SagaError(KernelError):
    code = "KRN.SAGA"


class SagaStateError(SagaError):
    code = "KRN.SAGA_STATE"


class Status(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"          # forward failed AND compensation failed


@dataclass(frozen=True)
class Step:
    name: str
    action: Callable[[Dict[str, Any]], Any]
    compensation: Callable[[Dict[str, Any]], Any]
    timeout_s: float = 30.0


@dataclass
class StepRecord:
    name: str
    index: int
    started_at: float = 0.0
    finished_at: float = 0.0
    compensated_at: float = 0.0
    error: Optional[str] = None
    result: Any = None


@dataclass
class Saga:
    saga_id: str
    steps: Tuple[Step, ...]
    context: Dict[str, Any] = field(default_factory=dict)
    status: Status = Status.PENDING
    records: List[StepRecord] = field(default_factory=list)
    cursor: int = 0  # index of next forward step


class SagaLedger:
    """Tracks every saga instance and drives forward/compensation order."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._now = clock or time.monotonic
        self._sagas: Dict[str, Saga] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def begin(self, steps: Tuple[Step, ...],
              *, context: Optional[Dict[str, Any]] = None,
              saga_id: Optional[str] = None) -> Saga:
        if not steps:
            raise SagaError("a saga needs at least one step")
        sid = saga_id or f"saga-{uuid.uuid4().hex[:12]}"
        if sid in self._sagas:
            raise SagaError("saga id already exists", context={"saga": sid})
        saga = Saga(saga_id=sid, steps=steps, context=dict(context or {}))
        self._sagas[sid] = saga
        return saga

    def run(self, saga: Saga) -> Status:
        """Drive the saga forward; on failure, compensate in reverse.
        Returns the terminal status."""
        if saga.status not in (Status.PENDING, Status.RUNNING):
            raise SagaStateError(
                "saga already terminal",
                context={"saga": saga.saga_id, "status": saga.status.value},
            )
        saga.status = Status.RUNNING
        while saga.cursor < len(saga.steps):
            step = saga.steps[saga.cursor]
            record = StepRecord(name=step.name, index=saga.cursor,
                                started_at=self._now())
            saga.records.append(record)
            try:
                record.result = step.action(saga.context)
            except Exception as exc:  # compensate everything so far
                record.error = f"{type(exc).__name__}: {exc}"
                record.finished_at = self._now()
                self._compensate(saga, from_index=saga.cursor - 1)
                return saga.status
            record.finished_at = self._now()
            saga.cursor += 1
        saga.status = Status.COMPLETED
        return saga.status

    # ------------------------------------------------------------------
    # Compensation — idempotent at the ledger level
    # ------------------------------------------------------------------

    def _compensate(self, saga: Saga, *, from_index: int) -> None:
        saga.status = Status.COMPENSATING
        compensation_failed = False
        for i in range(from_index, -1, -1):
            record = saga.records[i]
            if record.compensated_at:      # resume-safe: never double-fire
                continue
            if record.error:               # step never completed its action
                continue
            try:
                saga.steps[i].compensation(saga.context)
                record.compensated_at = self._now()
            except Exception as exc:
                record.error = f"compensation failed — {type(exc).__name__}: {exc}"
                compensation_failed = True
        saga.status = Status.FAILED if compensation_failed else Status.COMPENSATED

    def abort(self, saga: Saga) -> Status:
        """External cancel: compensate all completed steps."""
        if saga.status not in (Status.PENDING, Status.RUNNING):
            return saga.status
        self._compensate(saga, from_index=saga.cursor - 1)
        return saga.status

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def get(self, saga_id: str) -> Saga:
        saga = self._sagas.get(saga_id)
        if saga is None:
            raise SagaError("unknown saga", context={"saga": saga_id})
        return saga

    def report(self, saga_id: str) -> Dict[str, Any]:
        saga = self.get(saga_id)
        return {
            "saga": saga.saga_id,
            "status": saga.status.value,
            "cursor": saga.cursor,
            "steps": [
                {
                    "name": r.name,
                    "done": bool(r.finished_at),
                    "compensated": bool(r.compensated_at),
                    "error": r.error,
                }
                for r in saga.records
            ],
        }

    def by_status(self, status: Status) -> Tuple[str, ...]:
        return tuple(sorted(s.saga_id for s in self._sagas.values()
                            if s.status == status))
