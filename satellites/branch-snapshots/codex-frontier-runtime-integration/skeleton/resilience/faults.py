"""Failure taxonomy — classify agent faults and route recovery.

Wave-3 SOTA (2026 agentic-AI fault taxonomy work): recovery works when it
matches the fault *type*, not when every failure gets the same retry.
Five classes, each with a distinct strategy:

  TRANSIENT   — timeouts, rate limits, flaky deps     → bounded retry w/ backoff
  LOGIC       — wrong tool, bad plan, off-spec output  → re-plan, don't retry blindly
  CONTEXT     — missing/stale/garbled context          → re-retrieve, then retry once
  OUTPUT      — malformed or contract-violating output → repair/repair-then-retry
  PERMANENT   — auth, permissions, missing capability  → fail fast, surface cause

The taxonomy classifies from the exception surface (type + message shape)
so it needs no instrumentation changes; strategies return a structured
plan the caller executes. Pure domain, deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional


class FaultClass(str, Enum):
    TRANSIENT = "transient"
    LOGIC = "logic"
    CONTEXT = "context"
    OUTPUT = "output"
    PERMANENT = "permanent"


_TRANSIENT_PAT = re.compile(
    r"timeout|timed? ?out|rate.?limit|429|503|connection (reset|refused)|temporarily", re.I
)
_PERMANENT_PAT = re.compile(
    r"unauthorized|401|403|forbidden|permission|not.?found|no capable|unknown (lane|slot|capability)", re.I
)
_CONTEXT_PAT = re.compile(
    r"stale|out of date|missing context|empty (result|context)|not seeded|not wired", re.I
)
_OUTPUT_PAT = re.compile(
    r"json|parse|malformed|schema|validation|must return a dict|contract", re.I
)


@dataclass(frozen=True)
class RecoveryPlan:
    fault_class: FaultClass
    action: str                     # retry | replan | rerecord-context | repair | fail
    max_attempts: int
    backoff_s: float
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fault_class": self.fault_class.value,
            "action": self.action,
            "max_attempts": self.max_attempts,
            "backoff_s": self.backoff_s,
            "note": self.note,
        }


def classify(exc: BaseException) -> FaultClass:
    """Classify an exception into the fault taxonomy."""
    text = f"{type(exc).__name__}: {exc}"
    if _TRANSIENT_PAT.search(text):
        return FaultClass.TRANSIENT
    if _PERMANENT_PAT.search(text):
        return FaultClass.PERMANENT
    if _CONTEXT_PAT.search(text):
        return FaultClass.CONTEXT
    if _OUTPUT_PAT.search(text):
        return FaultClass.OUTPUT
    return FaultClass.LOGIC


def recovery_plan(exc: BaseException, *, attempt: int = 1) -> RecoveryPlan:
    """Map a fault to its recovery strategy, aware of the current attempt."""
    cls = classify(exc)
    if cls is FaultClass.TRANSIENT:
        return RecoveryPlan(cls, "retry", max_attempts=3,
                            backoff_s=min(30.0, 0.5 * (2 ** (attempt - 1))),
                            note="transient dependency — back off and retry")
    if cls is FaultClass.CONTEXT:
        return RecoveryPlan(cls, "rerecord-context", max_attempts=1,
                            backoff_s=0.0,
                            note="context stale or missing — refresh retrieval, retry once")
    if cls is FaultClass.OUTPUT:
        return RecoveryPlan(cls, "repair", max_attempts=2,
                            backoff_s=0.0,
                            note="output off-contract — repair shape, then retry")
    if cls is FaultClass.LOGIC:
        return RecoveryPlan(cls, "replan", max_attempts=1,
                            backoff_s=0.0,
                            note="plan or tool choice wrong — re-plan before retrying")
    return RecoveryPlan(cls, "fail", max_attempts=0, backoff_s=0.0,
                        note="permanent cause — surface, don't retry")
