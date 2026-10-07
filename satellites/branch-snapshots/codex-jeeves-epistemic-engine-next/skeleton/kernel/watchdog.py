"""Kernel watchdog — detects stalled work, not just dead processes.

The supervisor (supervisor.py) watches *agents*; the watchdog watches
*operations*. An agent can be perfectly alive and heartbeating while a
critical operation has silently wedged — a lock it never released, a
pipeline stage stuck in a retry loop, a saga that never settled.

- :class:`OperationLease` — opened when work starts, must be checked in
  on (progress pings) or closed within ``stall_after``.
- :meth:`Watchdog.sweep` — finds operations that went quiet, marks them
  STALLED, and raises :class:`StalledOperationError`-carrying incidents
  for the bus after ``escalate_after``.
- Cheap to run on every scheduler tick: O(open operations).

"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from .errors import KernelError


class WatchdogError(KernelError):
    code = "KRN.WATCHDOG"


class StalledOperationError(WatchdogError):
    code = "KRN.OP_STALLED"
    http_status = 504


class OpState(str, Enum):
    RUNNING = "RUNNING"
    STALLED = "STALLED"
    CLOSED = "CLOSED"


@dataclass
class OperationLease:
    op_id: str
    owner: str
    opened_at: float
    last_progress: float
    state: OpState = OpState.RUNNING
    note: str = ""
    escalated: bool = False


@dataclass(frozen=True)
class WatchdogIncident:
    op_id: str
    owner: str
    stalled_for_s: float
    escalated: bool
    note: str


class Watchdog:
    def __init__(
        self,
        *,
        stall_after_s: float = 30.0,
        escalate_after_s: float = 120.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if not 0 < stall_after_s < escalate_after_s:
            raise WatchdogError(
                "windows must satisfy 0 < stall < escalate",
                context={"stall": stall_after_s, "escalate": escalate_after_s},
            )
        self.stall_after_s = stall_after_s
        self.escalate_after_s = escalate_after_s
        self._now = clock or time.monotonic
        self._ops: Dict[str, OperationLease] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self, op_id: str, owner: str, *, note: str = "") -> OperationLease:
        existing = self._ops.get(op_id)
        if existing is not None and existing.state is not OpState.CLOSED:
            raise WatchdogError("operation already open", context={"op": op_id})
        now = self._now()
        op = OperationLease(op_id=op_id, owner=owner, opened_at=now,
                            last_progress=now, note=note)
        self._ops[op_id] = op
        return op

    def ping(self, op_id: str, *, note: str = "") -> None:
        op = self._require(op_id)
        op.last_progress = self._now()
        if note:
            op.note = note
        if op.state is OpState.STALLED:
            op.state = OpState.RUNNING  # recovered on its own

    def close(self, op_id: str) -> None:
        op = self._require(op_id)
        op.state = OpState.CLOSED

    # ------------------------------------------------------------------
    # Sweep
    # ------------------------------------------------------------------

    def sweep(self) -> Tuple[WatchdogIncident, ...]:
        now = self._now()
        out: List[WatchdogIncident] = []
        for op in self._ops.values():
            if op.state is OpState.CLOSED:
                continue
            quiet = now - op.last_progress
            if op.state is OpState.RUNNING and quiet >= self.stall_after_s:
                op.state = OpState.STALLED
                out.append(WatchdogIncident(op.op_id, op.owner,
                                            round(quiet, 3), False, op.note))
            elif op.state is OpState.STALLED and not op.escalated \
                    and quiet >= self.escalate_after_s:
                op.escalated = True
                out.append(WatchdogIncident(op.op_id, op.owner,
                                            round(quiet, 3), True, op.note))
        return tuple(out)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def stalled(self) -> Tuple[str, ...]:
        return tuple(sorted(o.op_id for o in self._ops.values()
                            if o.state is OpState.STALLED))

    def open_operations(self) -> Tuple[str, ...]:
        return tuple(sorted(o.op_id for o in self._ops.values()
                            if o.state is not OpState.CLOSED))

    def reap_closed(self, *, older_than_s: float = 3600.0) -> int:
        now = self._now()
        doomed = [k for k, o in self._ops.items()
                  if o.state is OpState.CLOSED
                  and now - o.last_progress > older_than_s]
        for k in doomed:
            del self._ops[k]
        return len(doomed)

    def _require(self, op_id: str) -> OperationLease:
        op = self._ops.get(op_id)
        if op is None:
            raise WatchdogError("unknown operation", context={"op": op_id})
        return op
