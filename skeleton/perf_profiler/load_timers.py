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
        if (budget_ms is not None and (
            isinstance(budget_ms, bool) or not isinstance(budget_ms, (int, float))
            or not math.isfinite(budget_ms) or budget_ms <= 0
        )):
            raise ValueError("budget_ms must be finite and positive")
        if type(label) is not str or not 1 <= len(label) <= 128:
            raise ValueError("load report label must be bounded text")
        self.label = label
        self.budget_ms = budget_ms
        self.clock: Clock = clock or MonotonicClock()
        self._roots: List[_Node] = []
        self._stack: List[_Node] = []
        self._errors: List[Dict[str, str]] = []

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        if type(name) is not str or not 1 <= len(name) <= 128 or "/" in name:
            raise ValueError("phase name must be bounded text without '/'")
        siblings = self._stack[-1].children if self._stack else self._roots
        if any(n.name == name for n in siblings):
            raise ValueError(f"duplicate phase name at this level: {name!r}")
        node = _Node(name=name, start_ms=self.clock.now_ms())
        siblings.append(node)
        self._stack.append(node)
        try:
            yield
        except BaseException as exc:
            path = "/".join(n.name for n in self._stack)
            self._errors.append({"phase": path, "error": type(exc).__name__})
            raise
        finally:
            end = self.clock.now_ms()
            if end < node.start_ms:
                raise RuntimeError("clock went backwards during phase")
            node.duration_ms = end - node.start_ms
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
