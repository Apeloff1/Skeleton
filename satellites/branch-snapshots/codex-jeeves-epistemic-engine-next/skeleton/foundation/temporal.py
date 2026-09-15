"""
Skeleton Foundation — Temporal Invariants (LTL-lite)

The InvariantLattice upgraded from one-shot predicates to temporal
logic over the event journal: invariants about SEQUENCES, not just
states. Safety, liveness, and response properties become checkable
— and violations point at the exact journal index where the trace
broke the property.

Operators (evaluated over the journal's event timeline):
- always(p):          p holds at EVERY step (safety)
- eventually(p):      p holds at SOME step within the window (liveness)
- never(p):           p holds at NO step
- until(p, q):        p holds at every step UNTIL q first holds
                      (and q must eventually hold)
- response(p, q):     whenever p holds, q eventually holds after it
- precedes(p, q):     if q ever holds, p held strictly before it

Evaluation:
- Over EventJournal entries directly (the canonical timeline), or
  over any list of timestamped states for standalone checks.
- Each violation returns a Trace — the minimal event window proving
  the failure — so debugging starts at evidence, not symptoms.
- The lattice registers temporal invariants beside classical ones
  and evaluates both in one pass; health() reports per-invariant
  traces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Trace:
    """Minimal evidence window proving a violation (or satisfaction)."""
    invariant: str
    violated: bool
    reason: str
    window: List[Dict[str, Any]] = field(default_factory=list)
    at_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"invariant": self.invariant, "violated": self.violated,
                "reason": self.reason, "at_index": self.at_index,
                "window_size": len(self.window)}


Predicate = Callable[[Dict[str, Any]], bool]


@dataclass
class TemporalInvariant:
    """One temporal property with its operator and predicates."""
    name: str
    operator: str  # always | eventually | never | until | response | precedes
    p: Predicate
    q: Optional[Predicate] = None
    severity: str = "ERROR"


class TemporalEvaluator:
    """Evaluates temporal invariants over an event timeline."""

    def evaluate(self, inv: TemporalInvariant,
                 timeline: List[Dict[str, Any]]) -> Trace:
        op = inv.operator
        if op == "always":
            return self._always(inv, timeline)
        if op == "eventually":
            return self._eventually(inv, timeline)
        if op == "never":
            return self._never(inv, timeline)
        if op == "until":
            return self._until(inv, timeline)
        if op == "response":
            return self._response(inv, timeline)
        if op == "precedes":
            return self._precedes(inv, timeline)
        return Trace(inv.name, True, f"unknown operator {op}")

    def _always(self, inv: TemporalInvariant, tl: List[Dict[str, Any]]) -> Trace:
        for i, event in enumerate(tl):
            if not inv.p(event):
                return Trace(inv.name, True, f"p failed at index {i}",
                             window=tl[max(0, i - 2):i + 1], at_index=i)
        return Trace(inv.name, False, "p held at every step")

    def _eventually(self, inv: TemporalInvariant, tl: List[Dict[str, Any]]) -> Trace:
        for i, event in enumerate(tl):
            if inv.p(event):
                return Trace(inv.name, False, f"p held at index {i}", at_index=i)
        return Trace(inv.name, True, "p never held in window", window=tl[-3:])

    def _never(self, inv: TemporalInvariant, tl: List[Dict[str, Any]]) -> Trace:
        for i, event in enumerate(tl):
            if inv.p(event):
                return Trace(inv.name, True, f"p held at index {i} (forbidden)",
                             window=tl[max(0, i - 1):i + 1], at_index=i)
        return Trace(inv.name, False, "p never held")

    def _until(self, inv: TemporalInvariant, tl: List[Dict[str, Any]]) -> Trace:
        if inv.q is None:
            return Trace(inv.name, True, "until requires q")
        for i, event in enumerate(tl):
            if inv.q(event):
                return Trace(inv.name, False, f"q reached at index {i} with p holding", at_index=i)
            if not inv.p(event):
                return Trace(inv.name, True, f"p failed at index {i} before q",
                             window=tl[max(0, i - 2):i + 1], at_index=i)
        return Trace(inv.name, True, "q never reached; p held throughout",
                     window=tl[-3:])

    def _response(self, inv: TemporalInvariant, tl: List[Dict[str, Any]]) -> Trace:
        if inv.q is None:
            return Trace(inv.name, True, "response requires q")
        for i, event in enumerate(tl):
            if inv.p(event):
                for j in range(i + 1, len(tl)):
                    if inv.q(tl[j]):
                        break
                else:
                    return Trace(inv.name, True,
                                 f"p at index {i} never answered by q",
                                 window=tl[i:i + 3], at_index=i)
        return Trace(inv.name, False, "every p answered by q")

    def _precedes(self, inv: TemporalInvariant, tl: List[Dict[str, Any]]) -> Trace:
        if inv.q is None:
            return Trace(inv.name, True, "precedes requires q")
        p_seen_at: Optional[int] = None
        for i, event in enumerate(tl):
            if p_seen_at is None and inv.p(event):
                p_seen_at = i
            if inv.q(event):
                if p_seen_at is None or p_seen_at >= i:
                    return Trace(inv.name, True,
                                 f"q at index {i} without p strictly before",
                                 window=tl[max(0, i - 2):i + 1], at_index=i)
                return Trace(inv.name, False, f"p at {p_seen_at} preceded q at {i}",
                             at_index=i)
        return Trace(inv.name, False, "q never held (vacuously true)")


class TemporalLattice:
    """Registers and evaluates temporal invariants over the journal."""

    def __init__(self, journal: Optional[Any] = None):
        self._journal = journal
        self._invariants: List[TemporalInvariant] = []
        self._evaluator = TemporalEvaluator()
        self._stats = {"registered": 0, "evaluations": 0}

    def register(self, invariant: TemporalInvariant) -> None:
        self._invariants.append(invariant)
        self._stats["registered"] += 1

    # --- DSL helpers --------------------------------------------------------

    def always(self, name: str, p: Predicate, severity: str = "ERROR") -> TemporalInvariant:
        inv = TemporalInvariant(name, "always", p, severity=severity)
        self.register(inv)
        return inv

    def eventually(self, name: str, p: Predicate, severity: str = "WARNING") -> TemporalInvariant:
        inv = TemporalInvariant(name, "eventually", p, severity=severity)
        self.register(inv)
        return inv

    def never(self, name: str, p: Predicate, severity: str = "ERROR") -> TemporalInvariant:
        inv = TemporalInvariant(name, "never", p, severity=severity)
        self.register(inv)
        return inv

    def until(self, name: str, p: Predicate, q: Predicate, severity: str = "ERROR") -> TemporalInvariant:
        inv = TemporalInvariant(name, "until", p, q, severity=severity)
        self.register(inv)
        return inv

    def response(self, name: str, p: Predicate, q: Predicate, severity: str = "ERROR") -> TemporalInvariant:
        inv = TemporalInvariant(name, "response", p, q, severity=severity)
        self.register(inv)
        return inv

    def precedes(self, name: str, p: Predicate, q: Predicate, severity: str = "ERROR") -> TemporalInvariant:
        inv = TemporalInvariant(name, "precedes", p, q, severity=severity)
        self.register(inv)
        return inv

    # --- Evaluation -------------------------------------------------------------

    def _timeline(self, timeline: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        if timeline is not None:
            return timeline
        if self._journal is None:
            return []
        return [{"index": e.index, "topic": e.topic, **e.payload}
                for e in self._journal.slice(0)]

    def evaluate_all(self,
                     timeline: Optional[List[Dict[str, Any]]] = None) -> List[Trace]:
        self._stats["evaluations"] += 1
        tl = self._timeline(timeline)
        return [self._evaluator.evaluate(inv, tl) for inv in self._invariants]

    def violations(self,
                   timeline: Optional[List[Dict[str, Any]]] = None) -> List[Trace]:
        return [t for t in self.evaluate_all(timeline) if t.violated]

    def healthy(self, timeline: Optional[List[Dict[str, Any]]] = None) -> bool:
        return not any(
            t.violated and self._invariants[i].severity == "ERROR"
            for i, t in enumerate(self.evaluate_all(timeline))
        )

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
