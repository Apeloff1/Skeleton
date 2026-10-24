"""B039 — Self-repair and bounded optimization.

Success criterion (game_creation_batches.json): "Agents can diagnose failed evals
and iteratively repair within strict mutation/time/cost budgets."

Depends on B031 (model capability router) and B038 (generation provenance); this
module consumes them through small typed seams (``RouteChoice`` and
``ProvenanceRecord``) so the loop stays deterministic and testable.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence


class BudgetExceeded(RuntimeError):
    """Raised when an attempted step would breach a hard budget."""


@dataclass(frozen=True)
class Budget:
    max_mutations: int
    max_seconds: float
    max_cost: float

    def __post_init__(self) -> None:
        if self.max_mutations < 0 or self.max_seconds < 0 or self.max_cost < 0:
            raise ValueError("budgets must be non-negative")


@dataclass(frozen=True)
class EvalFailure:
    check: str
    message: str
    severity: str = "error"  # error | warning


@dataclass(frozen=True)
class EvalResult:
    score: float
    failures: tuple[EvalFailure, ...] = ()

    @property
    def passed(self) -> bool:
        return not any(f.severity == "error" for f in self.failures)


@dataclass(frozen=True)
class Diagnosis:
    category: str
    checks: tuple[str, ...]
    hint: str


_CATEGORIES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("schema", ("schema", "type", "missing"), "fix structure/fields"),
    ("logic", ("assert", "logic", "rule", "invariant"), "fix gameplay logic"),
    ("performance", ("timeout", "perf", "latency", "budget"), "reduce cost/complexity"),
    ("safety", ("unsafe", "safety", "policy"), "remove unsafe content"),
)


def diagnose(result: EvalResult) -> tuple[Diagnosis, ...]:
    """Group failing checks into deterministic, ordered diagnoses."""
    buckets: dict[str, list[str]] = {}
    for f in result.failures:
        if f.severity != "error":
            continue
        text = f"{f.check} {f.message}".lower()
        cat = next((c for c, keys, _ in _CATEGORIES if any(k in text for k in keys)), "unknown")
        buckets.setdefault(cat, []).append(f.check)
    hints = {c: h for c, _, h in _CATEGORIES}
    order = [c for c, _, _ in _CATEGORIES] + ["unknown"]
    return tuple(
        Diagnosis(c, tuple(sorted(buckets[c])), hints.get(c, "manual review"))
        for c in order if c in buckets
    )


@dataclass(frozen=True)
class Mutation:
    """A proposed artifact change: a full replacement payload plus its cost."""
    target: str
    payload: Mapping[str, object]
    cost: float
    rationale: str = ""


@dataclass(frozen=True)
class RouteChoice:
    """B031 seam: which model/provider was routed for a repair step."""
    model: str
    provider: str
    unit_cost: float = 0.0


@dataclass(frozen=True)
class ProvenanceRecord:
    """B038 seam: provenance of one repair step."""
    step: int
    model: str
    provider: str
    input_digest: str
    output_digest: str
    diagnoses: tuple[str, ...]
    score_before: float
    score_after: float
    cost: float


@dataclass
class RepairOutcome:
    status: str  # repaired | exhausted | stalled | already_passing
    artifact: Mapping[str, object]
    best_score: float
    steps: int
    cost_spent: float
    seconds_spent: float
    provenance: list[ProvenanceRecord] = field(default_factory=list)
    stop_reason: str = ""


def digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


Evaluator = Callable[[Mapping[str, object]], EvalResult]
Proposer = Callable[[Mapping[str, object], Sequence[Diagnosis], RouteChoice], Mutation | None]
Router = Callable[[Sequence[Diagnosis]], RouteChoice]
Clock = Callable[[], float]


class RepairLoop:
    """Bounded diagnose→propose→evaluate loop with greedy (hill-climb) acceptance.

    Only improvements are kept, so the result is never worse than the input.
    Budgets are checked *before* each spend, so they are never exceeded.
    """

    def __init__(self, evaluator: Evaluator, proposer: Proposer, router: Router,
                 budget: Budget, clock: Clock, patience: int = 2) -> None:
        if patience < 1:
            raise ValueError("patience must be >= 1")
        self.evaluator, self.proposer, self.router = evaluator, proposer, router
        self.budget, self.clock, self.patience = budget, clock, patience

    def run(self, artifact: Mapping[str, object]) -> RepairOutcome:
        start = self.clock()
        current = dict(artifact)
        result = self.evaluator(current)
        out = RepairOutcome("already_passing", current, result.score, 0, 0.0, 0.0)
        if result.passed:
            out.stop_reason = "input passes evals"
            return out
        stale = 0
        while True:
            elapsed = self.clock() - start
            out.seconds_spent = elapsed
            if out.steps >= self.budget.max_mutations:
                return self._stop(out, "exhausted", "mutation budget")
            if elapsed >= self.budget.max_seconds:
                return self._stop(out, "exhausted", "time budget")
            diags = diagnose(result)
            route = self.router(diags)
            mutation = self.proposer(current, diags, route)
            if mutation is None:
                return self._stop(out, "stalled", "proposer has no candidate")
            cost = mutation.cost + route.unit_cost
            if cost < 0:
                raise ValueError("mutation cost must be non-negative")
            if out.cost_spent + cost > self.budget.max_cost:
                return self._stop(out, "exhausted", "cost budget")
            out.steps += 1
            out.cost_spent += cost
            candidate = dict(mutation.payload)
            new = self.evaluator(candidate)
            out.provenance.append(ProvenanceRecord(
                out.steps, route.model, route.provider, digest(current), digest(candidate),
                tuple(d.category for d in diags), result.score, new.score, cost))
            if new.score > result.score or (new.passed and not result.passed):
                current, result, stale = candidate, new, 0
                out.artifact, out.best_score = current, result.score
                if result.passed:
                    out.seconds_spent = self.clock() - start
                    return self._stop(out, "repaired", "evals pass")
            else:
                stale += 1
                if stale >= self.patience:
                    return self._stop(out, "stalled", "no improvement within patience")

    @staticmethod
    def _stop(out: RepairOutcome, status: str, reason: str) -> RepairOutcome:
        out.status, out.stop_reason = status, reason
        return out
