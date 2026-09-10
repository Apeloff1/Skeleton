"""
Skeleton Support — The Support Context System

The mirror fabric: for every primary context plane, an equally strong
support plane that observes, validates, heals, and optimizes it.
Spider-connected both ways — primaries publish state, supports consume,
diagnose, and feed corrections back.

Support planes (one per primary, same fixed size = 32 slots):

- SentinelContext   (mirrors WorkOrderContext) — validates every order
                    before execution: connector health, payload shape,
                    duplicate suppression, risk scoring
- HospiceContext    (mirrors BacklogContext)   — heals unfinished work:
                    retries with backoff, re-prioritization on age,
                    resurrection of expired items worth saving
- BlueprintContext  (mirrors PlanningContext)  — plan optimization:
                    critical path analysis, step merging, cost rebalancing,
                    parallel-lane detection
- ResonanceContext  (mirrors QueByPriority)    — queue harmonics:
                    starvation detection (items never dequeued),
                    weight rebalancing suggestions, fairness scoring
- LensContext       (mirrors OracleMatrix)     — prediction auditing:
                    tracks oracle accuracy, calibrates confidence,
                    flags systematic over/under-prediction
- WardContext       (mirrors ContextSyntaxFixer) — meta-repair:
                    audits the fixer itself, learns new repair rules
                    from repeated issue patterns

Every support plane is loaded on demand via the LoadingQueue — never
resident until its primary signals pressure.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


SUPPORT_SIZE = 32  # same fixed size as primary context planes


# ---------------------------------------------------------------------------
# Sentinel — work order validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationRecord:
    order_id: str
    verdict: str  # pass | warn | block
    risk: float
    reasons: List[str] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)


class SentinelContext:
    """Pre-execution validation for every work order."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self.records: List[ValidationRecord] = []
        self._seen_payloads: set = set()
        self._stats = {"validated": 0, "passed": 0, "warned": 0, "blocked": 0, "duplicates": 0}

    def validate(self, order: Any) -> ValidationRecord:
        self._stats["validated"] += 1
        reasons: List[str] = []
        risk = 0.0

        # Duplicate suppression
        sig = f"{order.connector}|{order.action}|{order.payload.get('context', '')[:60]}"
        if sig in self._seen_payloads:
            reasons.append("duplicate_order")
            risk += 0.4
            self._stats["duplicates"] += 1
        self._seen_payloads.add(sig)

        # Payload shape
        if not order.payload.get("context"):
            reasons.append("empty_payload_context")
            risk += 0.2

        # Priority sanity
        if order.priority > 8.0:
            reasons.append("suspiciously_high_priority")
            risk += 0.1

        # MAG context presence (enhanced orders are safer bets)
        if not order.mag_context:
            reasons.append("no_episodic_support")
            risk += 0.1

        risk = min(1.0, risk)
        verdict = "block" if risk >= 0.7 else "warn" if risk >= 0.3 else "pass"
        self._stats[{"pass": "passed", "warn": "warned", "block": "blocked"}[verdict]] += 1

        record = ValidationRecord(order_id=order.order_id, verdict=verdict, risk=risk, reasons=reasons)
        if len(self.records) >= SUPPORT_SIZE:
            self.records.pop(0)
        self.records.append(record)

        if self._bus and verdict == "block":
            self._bus.emit("support.sentinel.blocked", {"order_id": order.order_id, "risk": risk})
        return record

    def summary(self) -> Dict[str, Any]:
        return {"records": len(self.records), "capacity": SUPPORT_SIZE, **self._stats}


# ---------------------------------------------------------------------------
# Hospice — backlog healing
# ---------------------------------------------------------------------------

@dataclass
class HealAction:
    item_id: str
    action: str  # retry | reprioritize | resurrect | euthanize
    detail: str
    at: float = field(default_factory=time.time)


class HospiceContext:
    """Heals unfinished work in the backlog."""

    MAX_RETRIES = 3
    RESURRECT_AGE = 32

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self.actions: List[HealAction] = []
        self._retry_counts: Dict[str, int] = {}
        self._stats = {"healed": 0, "retried": 0, "reprioritized": 0, "resurrected": 0, "euthanized": 0}

    def heal(self, backlog: Any) -> List[HealAction]:
        """One healing pass over the backlog plane."""
        new_actions: List[HealAction] = []
        for item in list(backlog.items):
            action = None
            retries = self._retry_counts.get(item.item_id, 0)

            if item.age_cycles > self.RESURRECT_AGE and item.priority >= 5.0:
                item.priority = min(10.0, item.priority * 1.2)
                item.age_cycles = 0
                action = HealAction(item.item_id, "resurrect", "high-priority item revived with boosted priority")
                self._stats["resurrected"] += 1
            elif item.kind == "failed_order" and retries < self.MAX_RETRIES:
                self._retry_counts[item.item_id] = retries + 1
                item.priority *= 0.9  # slightly deprioritize retries
                action = HealAction(item.item_id, "retry", f"retry {retries + 1}/{self.MAX_RETRIES}")
                self._stats["retried"] += 1
            elif item.age_cycles > 16 and item.priority < 9.0:
                item.priority = min(10.0, item.priority + 0.5)
                action = HealAction(item.item_id, "reprioritize", "aged item given priority boost")
                self._stats["reprioritized"] += 1
            elif item.kind == "failed_order" and retries >= self.MAX_RETRIES and item.priority < 3.0:
                backlog.items.remove(item)
                action = HealAction(item.item_id, "euthanize", "unrecoverable low-priority item released")
                self._stats["euthanized"] += 1

            if action:
                new_actions.append(action)
                self._stats["healed"] += 1

        if len(self.actions) + len(new_actions) > SUPPORT_SIZE:
            self.actions = self.actions[-(SUPPORT_SIZE - len(new_actions)):]
        self.actions.extend(new_actions)

        if self._bus and new_actions:
            self._bus.emit("support.hospice.healed", {"actions": len(new_actions)})
        return new_actions

    def summary(self) -> Dict[str, Any]:
        return {"actions": len(self.actions), "capacity": SUPPORT_SIZE, **self._stats}


# ---------------------------------------------------------------------------
# Blueprint — plan optimization
# ---------------------------------------------------------------------------

class BlueprintContext:
    """Optimizes plans: critical path, step merging, parallel lanes."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._stats = {"optimized": 0, "merged": 0, "lanes_found": 0}

    def critical_path(self, plan: Any) -> List[str]:
        """Longest dependency chain by estimated cost."""
        steps = {s.step_id: s for s in plan.steps}
        memo: Dict[str, float] = {}
        memo_path: Dict[str, List[str]] = {}

        def cost_of(sid: str) -> float:
            if sid in memo:
                return memo[sid]
            step = steps.get(sid)
            if step is None:
                return 0.0
            if not step.depends_on:
                memo[sid] = step.estimated_cost
                memo_path[sid] = [sid]
            else:
                best_dep = max(step.depends_on, key=lambda d: cost_of(d))
                memo[sid] = step.estimated_cost + cost_of(best_dep)
                memo_path[sid] = memo_path.get(best_dep, []) + [sid]
            return memo[sid]

        if not steps:
            return []
        end = max(steps, key=cost_of)
        cost_of(end)
        return memo_path.get(end, [])

    def mergeable(self, plan: Any) -> List[tuple]:
        """Pairs of adjacent same-connector steps that merge cleanly."""
        pairs = []
        pending = [s for s in plan.steps if s.status == "pending"]
        for i in range(len(pending) - 1):
            a, b = pending[i], pending[i + 1]
            if a.connector and a.connector == b.connector and not b.depends_on:
                pairs.append((a.step_id, b.step_id))
        return pairs

    def parallel_lanes(self, plan: Any) -> List[List[str]]:
        """Groups of mutually independent steps that can run concurrently.""
        lanes: Dict[int, List[str]] = {}
        depth_cache: Dict[str, int] = {}

        def depth(sid: str) -> int:
            if sid in depth_cache:
                return depth_cache[sid]
            step = next((s for s in plan.steps if s.step_id == sid), None)
            if step is None or not step.depends_on:
                depth_cache[sid] = 0
            else:
                depth_cache[sid] = 1 + max(depth(d) for d in step.depends_on)
            return depth_cache[sid]

        for step in plan.steps:
            if step.status == "pending":
                d = depth(step.step_id)
                lanes.setdefault(d, []).append(step.step_id)
        result = [steps for _, steps in sorted(lanes.items()) if len(steps) > 1]
        self._stats["lanes_found"] += len(result)
        return result

    def optimize(self, plan: Any) -> Dict[str, Any]:
        self._stats["optimized"] += 1
        path = self.critical_path(plan)
        merges = self.mergeable(plan)
        lanes = self.parallel_lanes(plan)
        self._stats["merged"] += len(merges)
        if self._bus:
            self._bus.emit("support.blueprint.optimized", {
                "plan": plan.plan_id, "critical_steps": len(path), "merges": len(merges), "lanes": len(lanes),
            })
        return {"critical_path": path, "mergeable": merges, "parallel_lanes": lanes}

    def summary(self) -> Dict[str, Any]:
        return dict(self._stats)


# ---------------------------------------------------------------------------
# Resonance — queue harmonics
# ---------------------------------------------------------------------------

class ResonanceContext:
    """Queue health: starvation, fairness, weight suggestions."""

    STARVATION_CYCLES = 8

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._first_seen: Dict[str, float] = {}
        self._stats = {"scans": 0, "starving_found": 0, "suggestions": 0}

    def scan(self, queue: Any) -> Dict[str, Any]:
        self._stats["scans"] += 1
        now = time.time()
        starving = []
        for item in queue.items:
            self._first_seen.setdefault(item.item_id, now)
            age = now - self._first_seen[item.item_id]
            if age > self.STARVATION_CYCLES and item.blended < 0.3:
                starving.append(item.item_id)

        blends = [i.blended for i in queue.items]
        fairness = 1.0
        if len(blends) > 1:
            mean = sum(blends) / len(blends)
            variance = sum((b - mean) ** 2 for b in blends) / len(blends)
            fairness = 1.0 / (1.0 + variance * 10)

        suggestions = []
        if starving:
            self._stats["starving_found"] += len(starving)
            suggestions.append({"action": "boost_hazard_weight", "for": starving[:3],
                                "reason": "long-queued low-score items need hazard system boost"})
            self._stats["suggestions"] += 1
        if fairness < 0.7:
            suggestions.append({"action": "rebalance_weights", "reason": f"blend variance high (fairness {fairness:.2f})"})
            self._stats["suggestions"] += 1

        if self._bus and suggestions:
            self._bus.emit("support.resonance.suggestions", {"count": len(suggestions)})
        return {"starving": starving, "fairness": round(fairness, 3), "suggestions": suggestions}

    def summary(self) -> Dict[str, Any]:
        return dict(self._stats)


# ---------------------------------------------------------------------------
# Lens — oracle prediction auditing
# ---------------------------------------------------------------------------

class LensContext:
    """Audits oracle accuracy; calibrates confidence over time."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._predictions: List[Dict[str, Any]] = []
        self._stats = {"tracked": 0, "resolved": 0, "bias": 0.0}

    def track(self, reading: Any) -> None:
        self._predictions.append({
            "at": time.time(),
            "probability": reading.next_event_probability,
            "quality": reading.completion_forecast.get("projected_quality", 0.5),
            "resolved": None,
        })
        if len(self._predictions) > SUPPORT_SIZE:
            self._predictions.pop(0)
        self._stats["tracked"] += 1

    def resolve(self, realized_probability: float) -> None:
        """Mark the oldest unresolved prediction with its realized outcome."""
        for p in self._predictions:
            if p["resolved"] is None:
                p["resolved"] = realized_probability
                self._stats["resolved"] += 1
                break
        self._recompute_bias()

    def _recompute_bias(self) -> None:
        resolved = [p for p in self._predictions if p["resolved"] is not None]
        if not resolved:
            return
        errors = [p["probability"] - p["resolved"] for p in resolved]
        self._stats["bias"] = round(sum(errors) / len(errors), 4)

    def calibration(self) -> Dict[str, Any]:
        resolved = [p for p in self._predictions if p["resolved"] is not None]
        if not resolved:
            return {"calibrated": False, "samples": 0}
        errors = [abs(p["probability"] - p["resolved"]) for p in resolved]
        mae = sum(errors) / len(errors)
        return {
            "calibrated": mae < 0.2,
            "samples": len(resolved),
            "mean_absolute_error": round(mae, 4),
            "bias": self._stats["bias"],
            "verdict": "oracle over-predicts" if self._stats["bias"] > 0.1 else
                       "oracle under-predicts" if self._stats["bias"] < -0.1 else "oracle well-calibrated",
        }

    def summary(self) -> Dict[str, Any]:
        return {**self._stats, "calibration": self.calibration()}


# ---------------------------------------------------------------------------
# Ward — meta-repair for the syntax fixer
# ---------------------------------------------------------------------------

class WardContext:
    """Audits the syntax fixer; learns new repair rules from patterns."""

    LEARN_THRESHOLD = 3

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._rule_counts: Dict[str, int] = {}
        self.learned_rules: Dict[str, Dict[str, Any]] = {}
        self._stats = {"audits": 0, "rules_learned": 0}

    def audit(self, issues: List[Any]) -> Dict[str, Any]:
        self._stats["audits"] += 1
        for issue in issues:
            rule = getattr(issue, "rule", str(issue))
            self._rule_counts[rule] = self._rule_counts.get(rule, 0) + 1

        new_rules = []
        for rule, count in self._rule_counts.items():
            if count >= self.LEARN_THRESHOLD and rule not in self.learned_rules:
                self.learned_rules[rule] = {
                    "pattern": rule,
                    "occurrences": count,
                    "learned_at": time.time(),
                    "suggestion": f"prevent recurrence of '{rule}' at parse time",
                }
                new_rules.append(rule)
                self._stats["rules_learned"] += 1

        if self._bus and new_rules:
            self._bus.emit("support.ward.rules_learned", {"rules": new_rules})
        return {"rule_counts": dict(self._rule_counts), "learned": new_rules}

    def summary(self) -> Dict[str, Any]:
        return {**self._stats, "active_rules": len(self.learned_rules)}
