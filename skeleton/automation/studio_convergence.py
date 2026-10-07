"""Convergence signals for autonomous completion."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Convergence:
    status: str
    remaining: int
    blocked: int
    quarantined_lanes: int

def evaluate(*, queued:int, blocked:int, active_lanes:int, quarantined_lanes:int) -> Convergence:
    values=(queued,blocked,active_lanes,quarantined_lanes)
    if any(v<0 for v in values): raise ValueError("convergence counts cannot be negative")
    if queued==0 and blocked==0: status="complete"
    elif active_lanes==0 and queued>0: status="stalled"
    elif blocked>0: status="degraded"
    else: status="progressing"
    return Convergence(status, queued, blocked, quarantined_lanes)
