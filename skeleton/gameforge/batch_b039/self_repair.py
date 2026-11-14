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


def _finite_nonnegative(name: str, value: object) -> float:
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not math.isfinite(value) or value < 0):
        raise ValueError(f"{name} must be a finite non-negative number")
    return float(value)


@dataclass(frozen=True)
class Budget:
    max_mutations: int
    max_seconds: float
    max_cost: float

    def __post_init__(self) -> None:
        if type(self.max_mutations) is not int or self.max_mutations < 0:
            raise ValueError("max_mutations must be a non-negative integer")
        _finite_nonnegative("max_seconds", self.max_seconds)
        _finite_nonnegative("max_cost", self.max_cost)


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
        if (isinstance(self.score, bool) or not isinstance(self.score, (int, float))
                or not math.isfinite(self.score)):
            raise ValueError("evaluation score must be finite")

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

    def __post_init__(self) -> None:
        _finite_nonnegative("mutation cost", self.cost)


@dataclass(frozen=True)
class RouteChoice:
    """B031 seam: thin adapter over the frozen router contract's ``RoutingReceipt``.

    Kept for B039's public API; build one from a receipt with :meth:`from_receipt`.
    """
    model: str
    provider: str
    unit_cost: float = 0.0
    receipt: RoutingReceipt | None = None

    def __post_init__(self) -> None:
        _finite_nonnegative("route unit cost", self.unit_cost)

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
        if (isinstance(start, bool) or not isinstance(start, (int, float))
                or not math.isfinite(start)):
            raise ValueError("repair clock must provide finite timestamps")
        current = dict(artifact)
        result = self.evaluator(current)
        out = RepairOutcome("already_passing", current, result.score, 0, 0.0, 0.0)
        if result.passed:
            out.stop_reason = "input passes evals"
            return out
        stale = 0
        while True:
            elapsed = self.clock() - start
            if not math.isfinite(elapsed) or elapsed < 0:
                raise ValueError("repair clock must advance monotonically")
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
                    elapsed = self.clock() - start
                    if not math.isfinite(elapsed) or elapsed < 0:
                        raise ValueError("repair clock must advance monotonically")
                    out.seconds_spent = elapsed
                    return self._stop(out, "repaired", "evals pass")
            else:
                stale += 1
                if stale >= self.patience:
                    return self._stop(out, "stalled", "no improvement within patience")

    @staticmethod
    def _stop(out: RepairOutcome, status: str, reason: str) -> RepairOutcome:
        out.status, out.stop_reason = status, reason
        return out
