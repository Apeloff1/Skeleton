"""Tail percentile calculations with bounded positive nanosecond observations."""
from __future__ import annotations
from dataclasses import dataclass
from math import ceil
from .dataset import EvalError

@dataclass(frozen=True,slots=True)
class LatencySummary:
    samples:int
    p50_ns:int
    p90_ns:int
    p95_ns:int
    p99_ns:int
    max_ns:int


def summarize(values:tuple[int,...])->LatencySummary:
    if not values or len(values)>100000 or any(type(v) is not int or v<0 for v in values):
        raise EvalError('invalid latency observations')
    sorted_ns=sorted(values)
    def percentile(p:float)->int:
        return sorted_ns[max(0,ceil(len(sorted_ns)*p)-1)]
    return LatencySummary(len(sorted_ns),percentile(.5),percentile(.9),
                          percentile(.95),percentile(.99),sorted_ns[-1])
