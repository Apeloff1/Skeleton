"""Runtime profiling helpers: allocations, frame-time hitches, nested load timers.

Stdlib only. Percentile statistics are delegated to main's existing
``skeleton/ai/runtime/observability/profiler.py`` (see ``_stats``) rather than
reimplemented. Baselines and regression verdicts are out of scope here; they
live in the existing profile-record / latency-budget / perf-gate modules.
"""
from __future__ import annotations

from .alloc import AllocationTracker, AllocDiff, AllocScopeResult
from .clock import Clock, DeterministicClock, MonotonicClock
from .frames import FrameSampler, FrameStats, Hitch
from .load_timers import LoadReport, LoadTimer, verify_report

SCHEMA_ID = "perf_profiler.v1"

__all__ = [
    "SCHEMA_ID",
    "AllocDiff",
    "AllocScopeResult",
    "AllocationTracker",
    "Clock",
    "DeterministicClock",
    "FrameSampler",
    "FrameStats",
    "Hitch",
    "LoadReport",
    "LoadTimer",
    "MonotonicClock",
    "verify_report",
]
