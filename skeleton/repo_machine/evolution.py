"""Measure whether repository evolution improves machine organization."""
from __future__ import annotations

from dataclasses import dataclass

from .health import repository_health
from .metrics import structural_metrics
from .model import RepositoryModel
from .model_diff import compare_models


@dataclass(frozen=True, slots=True)
class EvolutionSignal:
    name: str
    before: float
    after: float
    direction: str
    weight: int
    improved: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "before": self.before,
            "after": self.after,
            "direction": self.direction,
            "weight": self.weight,
            "improved": self.improved,
        }


@dataclass(frozen=True, slots=True)
class EvolutionReport:
    score: int
    verdict: str
    signals: tuple[EvolutionSignal, ...]
    added_files: int
    removed_files: int
    changed_files: int
    new_cycles: int
    resolved_cycles: int
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "verdict": self.verdict,
            "signals": [item.as_dict() for item in self.signals],
            "added_files": self.added_files,
            "removed_files": self.removed_files,
            "changed_files": self.changed_files,
            "new_cycles": self.new_cycles,
            "resolved_cycles": self.resolved_cycles,
            "notes": list(self.notes),
        }


def _signal(
    name: str,
    before: float,
    after: float,
    *,
    direction: str,
    weight: int,
) -> EvolutionSignal:
    if direction == "higher":
        improved = after > before
    elif direction == "lower":
        improved = after < before
    else:
        raise ValueError("direction must be higher or lower")
    return EvolutionSignal(name, before, after, direction, weight, improved)


def evaluate_evolution(
    before: RepositoryModel,
    after: RepositoryModel,
) -> EvolutionReport:
    before_health = repository_health(before)
    after_health = repository_health(after)
    before_metrics = structural_metrics(before)
    after_metrics = structural_metrics(after)
    delta = compare_models(before, after)

    signals = (
        _signal("health_score", before_health.score, after_health.score, direction="higher", weight=5),
        _signal(
            "unclassified_ratio",
            before_metrics.unclassified_ratio,
            after_metrics.unclassified_ratio,
            direction="lower",
            weight=4,
        ),
        _signal(
            "cycle_count",
            before_metrics.cycle_count,
            after_metrics.cycle_count,
            direction="lower",
            weight=5,
        ),
        _signal(
            "largest_zone_line_share",
            before_metrics.largest_zone_line_share,
            after_metrics.largest_zone_line_share,
            direction="lower",
            weight=2,
        ),
        _signal(
            "zone_entropy",
            before_metrics.zone_entropy,
            after_metrics.zone_entropy,
            direction="higher",
            weight=1,
        ),
    )

    score = 50
    notes: list[str] = []
    for signal in signals:
        if signal.before == signal.after:
            continue
        score += signal.weight * (2 if signal.improved else -2)
    if delta.new_cycles:
        score -= min(25, len(delta.new_cycles) * 10)
        notes.append("new cross-zone dependency cycles were introduced")
    if delta.resolved_cycles:
        score += min(20, len(delta.resolved_cycles) * 8)
        notes.append("cross-zone dependency cycles were resolved")
    if delta.unclassified_delta > 0:
        score -= min(15, delta.unclassified_delta)
        notes.append("unclassified machine surface grew")
    elif delta.unclassified_delta < 0:
        score += min(15, abs(delta.unclassified_delta))
        notes.append("unclassified machine surface shrank")
    if after.truncated:
        score = min(score, 20)
        notes.append("after model is truncated")
    score = max(0, min(100, score))

    verdict = (
        "improved"
        if score >= 60
        else "regressed"
        if score <= 40
        else "mixed"
    )
    return EvolutionReport(
        score=score,
        verdict=verdict,
        signals=signals,
        added_files=len(delta.added_files),
        removed_files=len(delta.removed_files),
        changed_files=len(delta.changed_files),
        new_cycles=len(delta.new_cycles),
        resolved_cycles=len(delta.resolved_cycles),
        notes=tuple(notes),
    )
