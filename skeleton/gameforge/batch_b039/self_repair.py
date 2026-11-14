"""B039 — Self-repair and bounded optimization.

Success criterion (game_creation_batches.json): "Agents can diagnose failed evals
and iteratively repair within strict mutation/time/cost budgets."

Depends on B031 (model capability router) and B038 (generation provenance); this
module consumes them through small typed seams (``RouteChoice`` and
``ProvenanceRecord``) so the loop stays deterministic and testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable, Mapping, Sequence

from skeleton.frontier.runtime.model_router_contract import (
    ROUTER_INTERFACE_VERSION,
    RouteStatus,
    RouteTask,
    RoutingReceipt,
)
from skeleton.gameforge.batch_b038 import ProvenanceRecord, digest


class BudgetExceeded(RuntimeError):
    """Raised when an attempted step would breach a hard budget."""


@dataclass(frozen=True)
class Budget:
    max_mutations: int
    max_seconds: float
    max_cost: float

    def __post_init__(self) -> None:
        if type(self.max_mutations) is not int or self.max_mutations < 0:
            raise ValueError("mutation budget must be a non-negative integer")
        if any(
            type(n) not in (int, float) or not math.isfinite(n) or n < 0
            for n in (self.max_seconds, self.max_cost)
        ):
            raise ValueError("time and cost budgets must be finite non-negative numbers")


@dataclass(frozen=True)
class EvalFailure:
    check: str
    message: str
    severity: str = "error"  # error | warning


@dataclass(frozen=True)
class EvalResult:
    score: float
    failures: tuple[EvalFailure, ...] = ()

    def __post_init__(self) -> None:
        if type(self.score) not in (int, float) or not math.isfinite(self.score):
            raise ValueError("evaluation score must be a finite number")

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
    """B031 seam: thin adapter over the frozen router contract's ``RoutingReceipt``.

    Kept for B039's public API; build one from a receipt with :meth:`from_receipt`.
    """
    model: str
    provider: str
    unit_cost: float = 0.0
    receipt: RoutingReceipt | None = None

    @classmethod
    def from_receipt(cls, receipt: RoutingReceipt, model: str | None = None,
                     unit_cost: float | None = None) -> "RouteChoice":
        if receipt.schema_version != ROUTER_INTERFACE_VERSION:
            raise ValueError("unsupported router interface version")
        if receipt.status not in (RouteStatus.PLANNED, RouteStatus.OK):
            raise BudgetExceeded(f"no usable route: {receipt.status}")
        provider = receipt.served_by or receipt.selected_provider_id
        if provider is None:
            raise ValueError("receipt has no selected provider")
        cost = unit_cost if unit_cost is not None else (receipt.estimated_cost or 0.0)
        return cls(model or receipt.task_type, provider, float(cost), receipt)

    def as_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"model": self.model, "provider": self.provider,
                                  "unit_cost": self.unit_cost}
        if self.receipt is not None:
            out["receipt"] = self.receipt.as_dict()
        return out


def repair_route_task(diagnoses: Sequence[Diagnosis], request_id: str | None = None) -> RouteTask:
    """Build the B031 router request for a repair step from its diagnoses."""
    return RouteTask(task_type="gameforge.self_repair", request_id=request_id,
                     metadata={"diagnoses": [d.category for d in diagnoses]})


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
        if type(start) not in (int, float) or not math.isfinite(start):
            raise ValueError("repair clock must be finite")
        current = dict(artifact)
        result = self.evaluator(current)
        out = RepairOutcome("already_passing", current, result.score, 0, 0.0, 0.0)
        if result.passed:
            out.stop_reason = "input passes evals"
            return out
        stale = 0
        while True:
            elapsed = self.clock() - start
            if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
                raise ValueError("repair clock must be monotonic and finite")
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
            if any(
                type(c) not in (int, float) or not math.isfinite(c) or c < 0
                for c in (mutation.cost, route.unit_cost)
            ):
                raise ValueError("mutation and route costs must be finite non-negative")
            cost = mutation.cost + route.unit_cost
            if not math.isfinite(cost):
                raise ValueError("total mutation cost is not finite")
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
