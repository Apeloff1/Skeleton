"""Recovery executor — run a callable under the fault taxonomy, with repair hooks.

The taxonomy (``resilience/faults.py``) classifies and plans; this module
executes. ``recover(fn, repair=...)`` runs the callable, and on failure
follows the recovery plan for its fault class:

- TRANSIENT  → sleep(backoff) and retry, up to max_attempts
- CONTEXT    → call ``refresh_context`` once, then retry once
- OUTPUT     → call ``repair`` (e.g. ``Contract.repair``) and retry up to 2
- LOGIC      → call ``replan`` once, then retry once
- PERMANENT  → raise immediately with the plan attached

Every attempt, classification, and outcome lands in an attempt log the
caller can inspect — recovery that can't be audited isn't self-healing,
it's just retrying. Pure domain; sleep is injectable for tests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .faults import FaultClass, RecoveryPlan, recovery_plan


@dataclass
class AttemptRecord:
    attempt: int
    fault_class: Optional[str]
    action: Optional[str]
    error: Optional[str]
    ok: bool


@dataclass
class RecoveryOutcome:
    result: Any
    ok: bool
    attempts: List[AttemptRecord] = field(default_factory=list)
    final_plan: Optional[RecoveryPlan] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "attempts": [vars(a) for a in self.attempts],
            "final_plan": None if self.final_plan is None else self.final_plan.to_dict(),
        }


def recover(
    fn: Callable[[], Any],
    *,
    refresh_context: Optional[Callable[[], None]] = None,
    repair: Optional[Callable[[Any], Any]] = None,
    replan: Optional[Callable[[BaseException], Callable[[], Any]]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> RecoveryOutcome:
    """Run ``fn`` with taxonomy-driven recovery. Never raises for recoverable
    classes; PERMANENT faults propagate after the plan is recorded."""
    attempts: List[AttemptRecord] = []
    current = fn
    for attempt in range(1, 5):  # hard ceiling; plans are smaller
        try:
            result = current()
            attempts.append(AttemptRecord(attempt, None, None, None, True))
            return RecoveryOutcome(result=result, ok=True, attempts=attempts)
        except Exception as exc:  # noqa: BLE001 - classification is the point
            plan = recovery_plan(exc, attempt=attempt)
            attempts.append(AttemptRecord(
                attempt, plan.fault_class.value, plan.action,
                f"{type(exc).__name__}: {exc}", False,
            ))
            if plan.fault_class is FaultClass.PERMANENT:
                return RecoveryOutcome(result=None, ok=False,
                                       attempts=attempts, final_plan=plan)
            if plan.fault_class is FaultClass.TRANSIENT:
                if attempt >= plan.max_attempts:
                    return RecoveryOutcome(result=None, ok=False,
                                           attempts=attempts, final_plan=plan)
                sleep(plan.backoff_s)
                continue
            if plan.fault_class is FaultClass.CONTEXT:
                if refresh_context is None:
                    return RecoveryOutcome(result=None, ok=False,
                                           attempts=attempts, final_plan=plan)
                refresh_context()
                continue  # one retry; the loop's next failure ends it
            if plan.fault_class is FaultClass.OUTPUT:
                if repair is None:
                    return RecoveryOutcome(result=None, ok=False,
                                           attempts=attempts, final_plan=plan)
                repair(exc)
                if attempt >= 2:
                    return RecoveryOutcome(result=None, ok=False,
                                           attempts=attempts, final_plan=plan)
                continue
            if plan.fault_class is FaultClass.LOGIC:
                if replan is None:
                    return RecoveryOutcome(result=None, ok=False,
                                           attempts=attempts, final_plan=plan)
                current = replan(exc)
                continue
    return RecoveryOutcome(result=None, ok=False, attempts=attempts)
