"""Invariant lattice — assertions that run continuously against live state.

Unit tests assert properties at build time; the lattice asserts them at
*run* time. Every subsystem registers invariants — statements that must
hold whenever the system is quiescent — and the lattice evaluates them on
demand or on a cadence, publishing violations to the event bus.

This is the runtime immune system: an invariant firing means a subsystem
has drifted into a state its own design says is impossible, and the
violation report names exactly which invariant, which subject, and what
the offending state looked like.

Design laws
-----------
- Invariants are pure predicates over a snapshot callable the owner
  provides. They never mutate what they inspect.
- Evaluation is fail-safe: an invariant that raises is recorded as a
  violation (a broken invariant is itself a fault signal).
- The lattice holds no subsystem state; it holds only (name, subject,
  snapshot, predicate) tuples and the evaluation history.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from skeleton.kernel.errors import KernelError
from skeleton.kernel.events import DomainEvent, EventBus


class InvariantError(KernelError):
    code = "KRN.INVARIANT"


SnapshotFn = Callable[[], Any]
Predicate = Callable[[Any], bool]


@dataclass(frozen=True)
class Invariant:
    """One registered assertion."""
    name: str
    subject: str                    # which subsystem owns it, e.g. "memory.mag"
    snapshot: SnapshotFn            # how to read the live state
    predicate: Predicate            # must hold over the snapshot
    severity: str = "ERROR"         # matches kernel Severity names


@dataclass(frozen=True)
class Violation:
    invariant: str
    subject: str
    detail: str
    occurred_at: float = field(default_factory=time.time)


class InvariantLattice:
    """Registry + evaluator for runtime invariants."""

    def __init__(self, *, bus: Optional[EventBus] = None,
                 history: int = 256) -> None:
        self._invariants: Dict[Tuple[str, str], Invariant] = {}
        self._bus = bus
        self._violations: Deque[Violation] = deque(maxlen=history)
        self._evaluations = 0

    def register(self, invariant: Invariant) -> None:
        key = (invariant.subject, invariant.name)
        if key in self._invariants:
            raise InvariantError(
                "invariant already registered",
                context={"subject": invariant.subject, "name": invariant.name},
            )
        self._invariants[key] = invariant

    def evaluate(self, *, subject: Optional[str] = None) -> List[Violation]:
        """
        Evaluate every invariant (or one subject's) and return the violations.
        Publishes each new violation to the bus.
        """
        fresh: List[Violation] = []
        for key, inv in self._invariants.items():
            if subject is not None and inv.subject != subject:
                continue
            self._evaluations += 1
            try:
                holds = inv.predicate(inv.snapshot())
                detail = ""
            except Exception as exc:  # noqa: BLE001 - a broken invariant is a violation
                holds, detail = False, f"predicate raised {type(exc).__name__}: {exc}"
            if not holds:
                violation = Violation(
                    invariant=inv.name,
                    subject=inv.subject,
                    detail=detail or "predicate returned False",
                )
                self._violations.append(violation)
                fresh.append(violation)
                if self._bus:
                    self._bus.publish(
                        DomainEvent(
                            topic="kernel.invariant.violated",
                            payload={
                                "invariant": inv.name,
                                "subject": inv.subject,
                                "severity": inv.severity,
                                "detail": violation.detail,
                            },
                            correlation_id=f"inv_{inv.subject}_{inv.name}",
                        )
                    )
        return fresh

    def violations(self, *, subject: Optional[str] = None,
                   limit: int = 50) -> List[Violation]:
        items = [v for v in self._violations
                 if subject is None or v.subject == subject]
        return items[-limit:]

    def stats(self) -> Dict[str, Any]:
        return {
            "registered": len(self._invariants),
            "subjects": sorted({i.subject for i in self._invariants.values()}),
            "evaluations": self._evaluations,
            "violations_retained": len(self._violations),
        }
