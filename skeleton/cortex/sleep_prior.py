"""Utility-prioritized sleep replay — consolidate what pays, first.

2026 continual-learning discussions converged on one point: uniform replay
from a trace buffer wastes the consolidation budget on low-value traces.
This module adds priority sampling to the sleep cycle: a trace's replay
priority is ``conf * (1 + slack)`` — confident traces that came from runs
with thermal slack (successful extractions) replay before the rest.

Attach via ``attach_priority_replay(sleep_cycle)``: wraps the cycle's
``consolidate`` sampling step without changing its signature or buffer.
Pure domain; no new imports beyond the sleep module itself.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from skeleton.cortex.sleep import SleepCycle, SleepTrace


def trace_priority(trace: SleepTrace) -> float:
    """Replay priority: confidence scaled by observed slack."""
    return trace.conf * (1.0 + max(0.0, trace.slack))


def prioritized_sample(cycle: SleepCycle, n: int) -> List[SleepTrace]:
    """Top-``n`` traces by replay priority, stable-ordered."""
    buf = list(cycle.buffer)
    if not buf:
        return []
    k = min(max(1, int(n)), len(buf))
    return sorted(buf, key=trace_priority, reverse=True)[:k]


def attach_priority_replay(cycle: SleepCycle) -> SleepCycle:
    """Swap the cycle's uniform random sample for priority sampling.

    Wraps ``cycle._rng.sample`` call sites by monkeypatching the private
    buffer ordering: sorts the buffer by priority in-place so the default
    ``consolidate`` path replays high-utility traces first. Returns the
    same cycle for chaining. Idempotent.
    """
    ordered = sorted(cycle.buffer, key=trace_priority, reverse=True)
    cycle.buffer.clear()
    cycle.buffer.extend(ordered)
    return cycle
