"""Incremental achievement tracking for reusable game/runtime events.

Designed for server authority: counters are monotonic by default, achievements
unlock exactly once, and rewards are emitted as data rather than applied implicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class AchievementRule:
    id: str
    metric: str
    threshold: float
    reward: Mapping[str, Any] = field(default_factory=dict)
    hidden: bool = False


@dataclass(frozen=True, slots=True)
class AchievementUnlock:
    id: str
    metric: str
    value: float
    reward: dict[str, Any]


class AchievementEngine:
    def __init__(self, rules: Iterable[AchievementRule]) -> None:
        materialized = tuple(rules)
        if not materialized:
            raise ValueError("achievement engine requires rules")
        ids = [rule.id for rule in materialized]
        if any(not rid.strip() for rid in ids):
            raise ValueError("blank achievement id")
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate achievement id")
        for rule in materialized:
            if not rule.metric.strip():
                raise ValueError("achievement metric cannot be blank")
            if rule.threshold < 0:
                raise ValueError("achievement threshold cannot be negative")
        self.rules = {rule.id: rule for rule in materialized}
        self.metrics: dict[str, float] = {}
        self.unlocked: set[str] = set()

    def set_metric(self, metric: str, value: float, *, allow_decrease: bool = False) -> tuple[AchievementUnlock, ...]:
        if not metric.strip():
            raise ValueError("metric cannot be blank")
        numeric = float(value)
        previous = self.metrics.get(metric, 0.0)
        if not allow_decrease and numeric < previous:
            numeric = previous
        self.metrics[metric] = numeric
        return self._check(metric)

    def increment(self, metric: str, amount: float = 1.0) -> tuple[AchievementUnlock, ...]:
        if amount < 0:
            raise ValueError("increment amount cannot be negative")
        return self.set_metric(metric, self.metrics.get(metric, 0.0) + amount)

    def ingest(self, updates: Mapping[str, float], *, additive: bool = True) -> tuple[AchievementUnlock, ...]:
        unlocked: list[AchievementUnlock] = []
        for metric, value in updates.items():
            events = self.increment(metric, value) if additive else self.set_metric(metric, value)
            unlocked.extend(events)
        return tuple(unlocked)

    def _check(self, metric: str) -> tuple[AchievementUnlock, ...]:
        value = self.metrics.get(metric, 0.0)
        events: list[AchievementUnlock] = []
        for rule in self.rules.values():
            if rule.metric != metric or rule.id in self.unlocked:
                continue
            if value < rule.threshold:
                continue
            self.unlocked.add(rule.id)
            events.append(AchievementUnlock(rule.id, metric, value, dict(rule.reward)))
        return tuple(events)

    def progress(self, achievement_id: str) -> float:
        rule = self.rules[achievement_id]
        if rule.threshold == 0:
            return 1.0
        return min(1.0, self.metrics.get(rule.metric, 0.0) / rule.threshold)

    def snapshot(self) -> dict[str, Any]:
        return {
            "metrics": dict(sorted(self.metrics.items())),
            "unlocked": sorted(self.unlocked),
        }
