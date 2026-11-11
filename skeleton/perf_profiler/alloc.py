"""tracemalloc-based allocation tracking with per-scope bytes and peak."""
from __future__ import annotations

import tracemalloc
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterator, List, Tuple

MAX_SCOPE_DEPTH = 64
MAX_SCOPE_NODES = 4_096
MAX_SCOPE_NAME_LENGTH = 128


@dataclass(frozen=True)
class AllocDiff:
    location: str
    size_diff: int
    count_diff: int


@dataclass
class AllocScopeResult:
    name: str
    alloc_bytes: int = 0
    peak_bytes: int = 0
    top: Tuple[AllocDiff, ...] = ()
    children: List["AllocScopeResult"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "alloc_bytes": self.alloc_bytes,
            "peak_bytes": self.peak_bytes,
            "top": [asdict(d) for d in self.top],
            "children": [c.to_dict() for c in self.children],
        }


class AllocationTracker:
    """Measure net allocated bytes and peak growth for named scopes.

    * ``alloc_bytes``: traced memory at scope exit minus at entry (net
      retained). Negative values mean the scope freed more than it kept.
    * ``peak_bytes``: highest traced memory during the scope minus traced
      memory at entry. Nested scopes are handled by saving/restoring the
      tracemalloc peak so an inner scope never hides an outer peak.
    * ``top``: largest per-line size diffs between entry/exit snapshots
      (only when ``top_n > 0``; snapshots are costly).

    Starts tracemalloc if needed and stops it on ``close`` only if it started it.
    """

    def __init__(self, top_n: int = 0, frames: int = 1) -> None:
        # Validate before starting global tracemalloc; malformed direct callers
        # must not alter the process-wide tracing state or allocate huge traces.
        if type(top_n) is not int or not 0 <= top_n <= 100:
            raise ValueError("top_n must be a bounded non-negative integer")
        if type(frames) is not int or not 1 <= frames <= 25:
            raise ValueError("frames must be a bounded positive integer")
        self.top_n = top_n
        self._owns = False
        if not tracemalloc.is_tracing():
            tracemalloc.start(frames)
            self._owns = True
        self._stack: List[AllocScopeResult] = []
        self._child_peaks: List[int] = []  # parallel to _stack
        self.results: List[AllocScopeResult] = []
        self._scope_count = 0

    def close(self) -> None:
        if self._stack:
            raise RuntimeError("cannot close tracker with open scopes")
        if self._owns and tracemalloc.is_tracing():
            tracemalloc.stop()
        self._owns = False

    def __enter__(self) -> "AllocationTracker":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def scope(self, name: str) -> Iterator[AllocScopeResult]:
        # Reject untrusted names and unbounded nested/serial reports before
        # snapshotting or touching process-wide tracing state.
        if (type(name) is not str or not 1 <= len(name) <= MAX_SCOPE_NAME_LENGTH
                or "/" in name):
            raise ValueError("allocation scope name must be bounded text without '/'")
        if len(self._stack) >= MAX_SCOPE_DEPTH:
            raise ValueError("allocation scope nesting exceeds bounded depth")
        if self._scope_count >= MAX_SCOPE_NODES:
            raise ValueError("allocation scope count exceeds bounded node limit")
        if not tracemalloc.is_tracing():
            raise RuntimeError("tracemalloc is not tracing (tracker closed?)")
        result = AllocScopeResult(name=name)
        outer_peak = tracemalloc.get_traced_memory()[1]
        before_snap = tracemalloc.take_snapshot() if self.top_n else None
        tracemalloc.reset_peak()
        start, _ = tracemalloc.get_traced_memory()
        self._stack.append(result)
        self._child_peaks.append(0)
        self._scope_count += 1
        try:
            yield result
        finally:
            self._stack.pop()
            child_abs_peak = self._child_peaks.pop()
            current, peak = tracemalloc.get_traced_memory()
            result.alloc_bytes = current - start
            if before_snap is not None:
                after = tracemalloc.take_snapshot()
                result.top = _top_diffs(after, before_snap, self.top_n)
            # tracemalloc keeps one global peak and reset_peak() is the only
            # control, so each scope reports its absolute peak to its parent,
            # which folds it in (a child's reset must not hide earlier peaks).
            own_abs_peak = max(peak, child_abs_peak)
            result.peak_bytes = max(0, own_abs_peak - start)
            report_up = max(own_abs_peak, outer_peak)
            if self._stack:
                parent = self._stack[-1]
                parent.children.append(result)
                self._child_peaks[-1] = max(self._child_peaks[-1], report_up)
            else:
                self.results.append(result)

    def totals(self) -> Dict[str, int]:
        return {
            "alloc_bytes": sum(r.alloc_bytes for r in self.results),
            "peak_bytes": max((r.peak_bytes for r in self.results), default=0),
        }


def _top_diffs(after: tracemalloc.Snapshot, before: tracemalloc.Snapshot, n: int) -> Tuple[AllocDiff, ...]:
    filt = [tracemalloc.Filter(False, tracemalloc.__file__), tracemalloc.Filter(False, __file__)]
    stats = after.filter_traces(filt).compare_to(before.filter_traces(filt), "lineno")
    out: List[AllocDiff] = []
    for stat in stats[:n]:
        frame = stat.traceback[0]
        out.append(AllocDiff(f"{frame.filename}:{frame.lineno}", stat.size_diff, stat.count_diff))
    return tuple(out)
