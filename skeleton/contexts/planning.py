"""
Skeleton Contexts — Planning Context + Priority Queue

PlanningContext: decomposes a goal into ordered plan steps, each with
estimated cost, connector bindings, and completion state. Sized like
the other context planes.

QueByPriority: the adaptive response queue. Orders and responses are
queued by a blended priority-probability score, re-ranked as the
conversation evolves. Uses all 18 probability systems to score and
predict what should go next.

The 18 probability systems (each a small deterministic estimator):
 1.  frequency       — how often this action class appeared recently
 2.  recency         — exponential decay on last-use time
 3.  success_rate    — historical completion rate of the connector
 4.  momentum        — rate of change of success over recent window
 5.  urgency         — explicit priority passed in
 6.  dependency      — fraction of prerequisites already satisfied
 7.  bayesian        — beta-distribution posterior on success
 8.  markov          — transition likelihood from the last action
 9.  entropy         — information content of the action class
 10. hazard          — probability of failure if deferred further
 11. correlation     — co-occurrence with the current conversation topic
 12. consensus       — hive-mind agreement score for the action
 13. seasonality     — cyclic pattern match against hourly buckets
 14. regression      — linear trend fit on recent completions
 15. softmax         — normalized exponential of raw score
 16. softmax_rank    — rank-normalized variant
 17. thompson        — Thompson sampling draw for exploration
 18. expected_value  — priority × probability payoff estimate
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.events import DomainEvent, EventBus


PLAN_SIZE = 32  # same size as other context planes
QUEUE_SIZE = 32


# ---------------------------------------------------------------------------
# Planning Context
# ---------------------------------------------------------------------------

@dataclass
class PlanStep:
    """One step of a plan."""
    step_id: str
    description: str
    connector: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    estimated_cost: float = 1.0
    status: str = "pending"  # pending | active | done | skipped


@dataclass
class Plan:
    """An ordered decomposition of a goal."""
    plan_id: str
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def next_step(self) -> Optional[PlanStep]:
        """First pending step whose dependencies are all done."""
        done_ids = {s.step_id for s in self.steps if s.status == "done"}
        for step in self.steps:
            if step.status == "pending" and all(d in done_ids for d in step.depends_on):
                return step
        return None

    def progress(self) -> float:
        if not self.steps:
            return 1.0
        return sum(1 for s in self.steps if s.status == "done") / len(self.steps)


class PlanningContext:
    """Fixed-size plane of active plans."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self.plans: List[Plan] = []
        self._stats = {"planned": 0, "steps_completed": 0, "plans_completed": 0}

    def decompose(self, goal: str, steps: List[Dict[str, Any]]) -> Plan:
        """Create a plan from a goal and step specs."""
        plan = Plan(plan_id=str(uuid.uuid4())[:10], goal=goal)
        for i, spec in enumerate(steps):
            plan.steps.append(PlanStep(
                step_id=f"{plan.plan_id}-s{i}",
                description=spec.get("description", f"step {i}"),
                connector=spec.get("connector"),
                depends_on=spec.get("depends_on", []),
                estimated_cost=spec.get("estimated_cost", 1.0),
            ))
        if len(self.plans) >= PLAN_SIZE:
            self.plans.pop(0)
        self.plans.append(plan)
        self._stats["planned"] += 1
        if self._bus:
            self._bus.emit("contexts.planning.decomposed", {"goal": goal, "steps": len(steps)})
        return plan

    def complete_step(self, plan: Plan, step_id: str, skipped: bool = False) -> None:
        for step in plan.steps:
            if step.step_id == step_id:
                step.status = "skipped" if skipped else "done"
                self._stats["steps_completed"] += 1
        if plan.progress() >= 1.0:
            self._stats["plans_completed"] += 1

    def active_plans(self) -> List[Plan]:
        return [p for p in self.plans if p.progress() < 1.0]

    def summary(self) -> Dict[str, Any]:
        return {
            "plans": len(self.plans),
            "active": len(self.active_plans()),
            "capacity": PLAN_SIZE,
            **self._stats,
        }


# ---------------------------------------------------------------------------
# The 18 probability systems
# ---------------------------------------------------------------------------

class ProbabilityField:
    """Deterministic estimators for action scoring. All take (record, now)."""

    @staticmethod
    def frequency(rec: Dict[str, Any], now: float) -> float:
        return min(1.0, rec.get("appearances", 0) / 10.0)

    @staticmethod
    def recency(rec: Dict[str, Any], now: float) -> float:
        age = max(0.0, now - rec.get("last_seen", now))
        return math.exp(-age / 3600.0)

    @staticmethod
    def success_rate(rec: Dict[str, Any], now: float) -> float:
        done = rec.get("done", 0)
        total = rec.get("attempts", 0)
        return done / total if total else 0.5

    @staticmethod
    def momentum(rec: Dict[str, Any], now: float) -> float:
        recent = rec.get("recent_outcomes", [])
        if len(recent) < 2:
            return 0.5
        half = len(recent) // 2
        early = sum(recent[:half]) / max(1, half)
        late = sum(recent[half:]) / max(1, len(recent) - half)
        return min(1.0, max(0.0, 0.5 + (late - early)))

    @staticmethod
    def urgency(rec: Dict[str, Any], now: float) -> float:
        return min(1.0, rec.get("priority", 1.0) / 10.0)

    @staticmethod
    def dependency(rec: Dict[str, Any], now: float) -> float:
        deps = rec.get("dependencies_total", 0)
        if deps == 0:
            return 1.0
        return rec.get("dependencies_met", 0) / deps

    @staticmethod
    def bayesian(rec: Dict[str, Any], now: float) -> float:
        alpha = 1 + rec.get("done", 0)
        beta = 1 + rec.get("attempts", 0) - rec.get("done", 0)
        return alpha / (alpha + beta)

    @staticmethod
    def markov(rec: Dict[str, Any], now: float) -> float:
        transitions = rec.get("transitions", {})
        last = rec.get("last_action", "")
        return transitions.get(last, 0.5)

    @staticmethod
    def entropy(rec: Dict[str, Any], now: float) -> float:
        dist = rec.get("class_distribution", {})
        total = sum(dist.values())
        if total == 0:
            return 0.5
        h = 0.0
        for count in dist.values():
            p = count / total
            if p > 0:
                h -= p * math.log2(p)
        return min(1.0, h / 4.0)

    @staticmethod
    def hazard(rec: Dict[str, Any], now: float) -> float:
        age_cycles = rec.get("age_cycles", 0)
        return min(1.0, age_cycles / 16.0)

    @staticmethod
    def correlation(rec: Dict[str, Any], now: float) -> float:
        topic_terms = set(rec.get("topic_terms", []))
        action_terms = set(rec.get("action_terms", []))
        if not topic_terms or not action_terms:
            return 0.5
        return len(topic_terms & action_terms) / len(topic_terms | action_terms)

    @staticmethod
    def consensus(rec: Dict[str, Any], now: float) -> float:
        votes = rec.get("hive_votes", [])
        return sum(votes) / len(votes) if votes else 0.5

    @staticmethod
    def seasonality(rec: Dict[str, Any], now: float) -> float:
        hourly = rec.get("hourly_hits", {})
        hour = time.gmtime(now).tm_hour
        peak = max(hourly.values()) if hourly else 0
        if peak == 0:
            return 0.5
        return hourly.get(str(hour), 0) / peak

    @staticmethod
    def regression(rec: Dict[str, Any], now: float) -> float:
        points = rec.get("completion_series", [])
        n = len(points)
        if n < 3:
            return 0.5
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(points) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, points))
        den = sum((x - mean_x) ** 2 for x in xs) or 1.0
        slope = num / den
        return min(1.0, max(0.0, 0.5 + slope))

    @staticmethod
    def softmax(rec: Dict[str, Any], now: float) -> float:
        raw = rec.get("raw_score", 0.0)
        return 1.0 / (1.0 + math.exp(-raw))

    @staticmethod
    def softmax_rank(rec: Dict[str, Any], now: float) -> float:
        rank = rec.get("rank", 0)
        total = max(1, rec.get("rank_total", 1))
        return 1.0 - (rank / total)

    @staticmethod
    def thompson(rec: Dict[str, Any], now: float) -> float:
        # Deterministic pseudo-sample: hash-seeded beta draw
        import random
        seed = hash((rec.get("action", ""), int(now // 60))) & 0xFFFFFFFF
        rng = random.Random(seed)
        alpha = 1 + rec.get("done", 0)
        beta = 1 + rec.get("attempts", 0) - rec.get("done", 0)
        return rng.betavariate(alpha, beta)

    @staticmethod
    def expected_value(rec: Dict[str, Any], now: float) -> float:
        p = rec.get("priority", 1.0)
        done = rec.get("done", 0)
        total = rec.get("attempts", 0)
        prob = done / total if total else 0.5
        return min(1.0, (p / 10.0) * prob * 2.0)


PROBABILITY_SYSTEMS: List[Tuple[str, Callable[[Dict[str, Any], float], float]]] = [
    ("frequency", ProbabilityField.frequency),
    ("recency", ProbabilityField.recency),
    ("success_rate", ProbabilityField.success_rate),
    ("momentum", ProbabilityField.momentum),
    ("urgency", ProbabilityField.urgency),
    ("dependency", ProbabilityField.dependency),
    ("bayesian", ProbabilityField.bayesian),
    ("markov", ProbabilityField.markov),
    ("entropy", ProbabilityField.entropy),
    ("hazard", ProbabilityField.hazard),
    ("correlation", ProbabilityField.correlation),
    ("consensus", ProbabilityField.consensus),
    ("seasonality", ProbabilityField.seasonality),
    ("regression", ProbabilityField.regression),
    ("softmax", ProbabilityField.softmax),
    ("softmax_rank", ProbabilityField.softmax_rank),
    ("thompson", ProbabilityField.thompson),
    ("expected_value", ProbabilityField.expected_value),
]


@dataclass
class QueuedItem:
    """An item in the priority queue with its 18-system scorecard."""
    item_id: str
    kind: str  # response | workorder | plan_step | backlog_resume
    payload: Any = None
    record: Dict[str, Any] = field(default_factory=dict)
    enqueued_at: float = field(default_factory=time.time)
    scorecard: Dict[str, float] = field(default_factory=dict)
    blended: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"item_id": self.item_id, "kind": self.kind, "blended": round(self.blended, 4)}


class QueByPriority:
    """Adaptive response queue scored by all 18 probability systems.

    Each item carries a record dict feeding the estimators; the queue
    re-blends scores on every dequeue so it adapts to the conversation
    as outcomes accumulate.
    """

    def __init__(self, bus: Optional[EventBus] = None, weights: Optional[Dict[str, float]] = None):
        self._bus = bus
        self.items: List[QueuedItem] = []
        # Default: uniform weights across the 18 systems
        self._weights = weights or {name: 1.0 / len(PROBABILITY_SYSTEMS) for name, _ in PROBABILITY_SYSTEMS}
        self._stats = {"enqueued": 0, "dequeued": 0, "reranked": 0}

    def score(self, record: Dict[str, Any]) -> Dict[str, float]:
        """Run all 18 systems over a record."""
        now = time.time()
        return {name: fn(record, now) for name, fn in PROBABILITY_SYSTEMS}

    def blend(self, scorecard: Dict[str, float]) -> float:
        return sum(scorecard.get(name, 0.5) * w for name, w in self._weights.items())

    def enqueue(self, kind: str, payload: Any, record: Optional[Dict[str, Any]] = None) -> QueuedItem:
        rec = record or {}
        item = QueuedItem(
            item_id=str(uuid.uuid4())[:10],
            kind=kind,
            payload=payload,
            record=rec,
        )
        item.scorecard = self.score(rec)
        item.blended = self.blend(item.scorecard)
        if len(self.items) >= QUEUE_SIZE:
            self.items.pop(0)
        self.items.append(item)
        self._stats["enqueued"] += 1
        if self._bus:
            self._bus.emit("contexts.queue.enqueued", {"kind": kind, "blended": item.blended})
        return item

    def rerank(self) -> None:
        """Re-blend every item (call after outcomes change)."""
        for item in self.items:
            item.scorecard = self.score(item.record)
            item.blended = self.blend(item.scorecard)
        self._stats["reranked"] += 1

    def dequeue(self) -> Optional[QueuedItem]:
        """Pop the highest-blended item."""
        if not self.items:
            return None
        self.rerank()
        best = max(self.items, key=lambda i: i.blended)
        self.items.remove(best)
        self._stats["dequeued"] += 1
        return best

    def peek(self, n: int = 5) -> List[QueuedItem]:
        return sorted(self.items, key=lambda i: i.blended, reverse=True)[:n]

    def adapt_weights(self, outcome_scores: Dict[str, float]) -> None:
        """Nudge weights toward systems that predicted the outcome well."""
        for name in self._weights:
            if name in outcome_scores:
                self._weights[name] = min(0.25, max(0.01, self._weights[name] * (0.9 + 0.2 * outcome_scores[name])))
        total = sum(self._weights.values()) or 1.0
        self._weights = {k: v / total for k, v in self._weights.items()}

    def summary(self) -> Dict[str, Any]:
        return {
            "queued": len(self.items),
            "capacity": QUEUE_SIZE,
            "systems": len(PROBABILITY_SYSTEMS),
            "top": [i.to_dict() for i in self.peek(3)],
            **self._stats,
        }
