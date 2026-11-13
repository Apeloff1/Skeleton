"""Nested scoped load timers producing a sealed (sha256) report."""
from __future__ import annotations

import hashlib
import json
import math
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from .clock import Clock, MonotonicClock

REPORT_SCHEMA = "perf_profiler.load_report.v1"
MAX_PHASE_DEPTH = 64
MAX_PHASE_NODES = 4_096


def _clock_reading(clock: Clock) -> float:
    """Reject malformed or overflowing clock values before mutating the tree."""
    raw = clock.now_ms()
    if type(raw) not in (int, float):
        raise ValueError("load clock timestamp must be finite")
    try:
        value = float(raw)
    except OverflowError as exc:
        raise ValueError("load clock timestamp must be finite") from exc
    if not math.isfinite(value):
        raise ValueError("load clock timestamp must be finite")
    return value



@dataclass
class _Node:
    name: str
    start_ms: float
    duration_ms: Optional[float] = None
    children: List["_Node"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        child_total = sum(c.duration_ms or 0.0 for c in self.children)
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms or 0.0, 6),
            "self_ms": round(max(0.0, (self.duration_ms or 0.0) - child_total), 6),
            "children": [c.to_dict() for c in self.children],
        }


@dataclass(frozen=True)
class LoadReport:
    payload: Dict[str, Any]
    digest: str

    def to_dict(self) -> Dict[str, Any]:
        return {"payload": self.payload, "sha256": self.digest}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)


def _canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def seal(payload: Dict[str, Any]) -> LoadReport:
    return LoadReport(payload=payload, digest=hashlib.sha256(_canonical(payload)).hexdigest())


def verify_report(data: Dict[str, Any]) -> bool:
    """True only if ``data`` is a well-formed report whose digest matches."""
    try:
        payload, digest = data["payload"], data["sha256"]
        if not isinstance(payload, dict) or payload.get("schema") != REPORT_SCHEMA:
            return False
        return isinstance(digest, str) and hashlib.sha256(_canonical(payload)).hexdigest() == digest
    except (KeyError, TypeError, ValueError):
        return False


class LoadTimer:
    """Time nested load phases::

        timer = LoadTimer(clock=DeterministicClock(script=[...]))
        with timer.phase("level"):
            with timer.phase("textures"): ...
        report = timer.report()

    ``report()`` refuses to seal while any phase is still open or when a phase
    raised (the error is recorded and the report is marked ``ok: False``).
    """

    def __init__(self, label: str = "load", clock: Optional[Clock] = None, budget_ms: Optional[float] = None) -> None:
        if budget_ms is not None:
            if type(budget_ms) not in (int, float):
                raise ValueError("budget_ms must be finite and positive")
            try:
                budget_ms = float(budget_ms)
            except OverflowError as exc:
                raise ValueError("budget_ms must be finite and positive") from exc
            if not math.isfinite(budget_ms) or budget_ms <= 0:
                raise ValueError("budget_ms must be finite and positive")
        if type(label) is not str or not 1 <= len(label) <= 128:
            raise ValueError("load report label must be bounded text")
        self.label = label
        self.budget_ms = budget_ms
        self.clock: Clock = clock or MonotonicClock()
        self._roots: List[_Node] = []
        self._stack: List[_Node] = []
        self._errors: List[Dict[str, str]] = []
        self._node_count = 0

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        if type(name) is not str or not 1 <= len(name) <= 128 or "/" in name:
            raise ValueError("phase name must be bounded text without '/'")
        if len(self._stack) >= MAX_PHASE_DEPTH:
            raise ValueError("load phase nesting exceeds bounded depth")
        if self._node_count >= MAX_PHASE_NODES:
            raise ValueError("load phase count exceeds bounded node limit")
        siblings = self._stack[-1].children if self._stack else self._roots
        if any(n.name == name for n in siblings):
            raise ValueError(f"duplicate phase name at this level: {name!r}")
        # Read and validate the clock before publishing a new node.
        node = _Node(name=name, start_ms=_clock_reading(self.clock))
        siblings.append(node)
        self._stack.append(node)
        self._node_count += 1
        body_failed = False
        try:
            yield
        except BaseException as exc:
            body_failed = True
            path = "/".join(n.name for n in self._stack)
            self._errors.append({"phase": path, "error": type(exc).__name__})
            raise
        finally:
            try:
                end = _clock_reading(self.clock)
                duration = end - node.start_ms
                if not math.isfinite(duration) or duration < 0:
                    raise ValueError("load clock must advance by a finite non-negative duration")
                node.duration_ms = duration
            except BaseException as exc:
                path = "/".join(n.name for n in self._stack)
                self._errors.append({"phase": path, "error": type(exc).__name__})
                # Preserve the original body exception if both body and clock fail.
                if not body_failed:
                    raise
            finally:
                self._stack.pop()

    def report(self) -> LoadReport:
        if self._stack:
            raise RuntimeError(f"phase still open: {self._stack[-1].name!r}")
        tree = [n.to_dict() for n in self._roots]
        phases: List[Dict[str, Any]] = []

        def walk(nodes: List[Dict[str, Any]], prefix: str) -> None:
            for n in nodes:
                path = f"{prefix}{n['name']}"
                phases.append({"name": path, "duration_ms": n["duration_ms"], "self_ms": n["self_ms"]})
                walk(n["children"], path + "/")

        walk(tree, "")
        total = round(sum(n["duration_ms"] for n in tree), 6)
        if not math.isfinite(total):
            raise ValueError("load report total exceeds finite bound")
        payload: Dict[str, Any] = {
            "schema": REPORT_SCHEMA,
            "label": self.label,
            "total_ms": total,
            "budget_ms": self.budget_ms,
            "ok": not self._errors and (self.budget_ms is None or total <= self.budget_ms),
            "errors": list(self._errors),
            "phases": phases,
            "tree": tree,
        }
        return seal(payload)
