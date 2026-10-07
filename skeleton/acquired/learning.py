"""Adaptive learning primitives mined and evolved from Tutolage v15.

This module intentionally extracts the reusable learning mechanics from the
older application layer instead of importing its FastAPI/MongoDB/Expo stack.
It keeps Skeleton's core dependency-light and exposes deterministic,
testable primitives that can be wired into Jeeves or any agent through the
canonical EventBus.

Mined concepts:
- Zone of Proximal Development (ZPD) classification
- adaptive difficulty recommendations
- graduated scaffolding
- XP/level progression

The implementation tightens several edge cases in the source design:
- zone predicates are mutually exclusive
- all user supplied numeric signals are bounded
- XP level calculations do not depend on a finite lookup table
- empty histories have stable defaults
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import fmean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from skeleton.kernel.events import EventBus


class DifficultyZone(str, Enum):
    """Current challenge band for a learner."""

    COMFORT = "comfort"
    GROWTH = "growth"
    STRETCH = "stretch"
    PANIC = "panic"


class ScaffoldType(str, Enum):
    """Supported assistance styles."""

    HINT = "hint"
    ANALOGY = "analogy"
    STEP_BY_STEP = "step_by_step"
    WORKED_EXAMPLE = "worked_example"
    BREAKDOWN = "breakdown"


@dataclass(frozen=True)
class LearningSignal:
    """Signals used to estimate the learner's present challenge zone.

    Scores use the inclusive [0.0, 1.0] range.  Time is measured in seconds.
    The engine clamps out-of-range values rather than allowing noisy telemetry
    to destabilize recommendations.
    """

    current_mastery: float = 0.5
    recent_performance: Tuple[float, ...] = field(default_factory=tuple)
    time_on_task: int = 0
    errors_made: int = 0
    hints_used: int = 0


@dataclass(frozen=True)
class ZPDResult:
    """Normalized ZPD analysis result."""

    zone: DifficultyZone
    average_performance: float
    performance_consistency: float
    struggle_score: float
    optimal_min: float
    optimal_max: float
    sweet_spot: float
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_zone": self.zone.value,
            "average_performance": self.average_performance,
            "performance_consistency": self.performance_consistency,
            "struggle_score": self.struggle_score,
            "optimal_difficulty_range": {
                "min": self.optimal_min,
                "max": self.optimal_max,
                "sweet_spot": self.sweet_spot,
            },
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class Scaffold:
    """A single assistance action."""

    type: ScaffoldType
    priority: int
    trigger: str
    content: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "priority": self.priority,
            "when_to_show": self.trigger,
            "content": self.content,
        }


class AdaptiveLearningEngine:
    """Dependency-light adaptive learning engine for Skeleton/Jeeves.

    The scoring model is intentionally transparent.  It combines performance,
    error count, hint reliance and unusually long task duration into a bounded
    struggle score, then uses mutually exclusive thresholds for zone selection.
    """

    _ZONE_RECOMMENDATIONS = {
        DifficultyZone.COMFORT: "increase_difficulty",
        DifficultyZone.GROWTH: "maintain",
        DifficultyZone.STRETCH: "add_scaffolding",
        DifficultyZone.PANIC: "reduce_difficulty",
    }

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._analyses = 0

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    @classmethod
    def _bounded_history(cls, values: Sequence[float]) -> Tuple[float, ...]:
        recent = tuple(cls._clamp(v) for v in values[-10:])
        return recent or (0.5,)

    @classmethod
    def _struggle_score(
        cls,
        average_performance: float,
        time_on_task: int,
        errors_made: int,
        hints_used: int,
    ) -> float:
        # Performance contributes most because it is the strongest direct
        # signal.  The other dimensions are normalized to saturate gradually.
        performance_gap = cls._clamp((0.70 - average_performance) / 0.70)
        error_pressure = cls._clamp(max(errors_made, 0) / 10.0)
        hint_pressure = cls._clamp(max(hints_used, 0) / 6.0)
        time_pressure = cls._clamp((max(time_on_task, 0) - 900) / 1800.0)
        score = (
            performance_gap * 0.40
            + error_pressure * 0.25
            + hint_pressure * 0.20
            + time_pressure * 0.15
        )
        return round(cls._clamp(score), 3)

    @staticmethod
    def _zone(average_performance: float, struggle_score: float) -> DifficultyZone:
        if average_performance >= 0.90 and struggle_score <= 0.15:
            return DifficultyZone.COMFORT
        if average_performance >= 0.70 and struggle_score <= 0.35:
            return DifficultyZone.GROWTH
        if average_performance >= 0.50 and struggle_score <= 0.65:
            return DifficultyZone.STRETCH
        return DifficultyZone.PANIC

    @classmethod
    def _difficulty_window(
        cls, mastery: float, zone: DifficultyZone
    ) -> Tuple[float, float, float]:
        mastery = cls._clamp(mastery)
        # Nudge the target depending on the observed zone.  Growth keeps the
        # learner slightly above mastery, comfort moves farther ahead, and
        # panic deliberately backs off.
        shift = {
            DifficultyZone.COMFORT: 0.10,
            DifficultyZone.GROWTH: 0.05,
            DifficultyZone.STRETCH: -0.05,
            DifficultyZone.PANIC: -0.15,
        }[zone]
        center = cls._clamp(mastery + shift, 0.05, 0.95)
        low = cls._clamp(center - 0.10, 0.05, 1.0)
        high = cls._clamp(center + 0.10, 0.05, 1.0)
        return round(low, 3), round(high, 3), round((low + high) / 2, 3)

    def analyze(self, signal: LearningSignal) -> ZPDResult:
        """Classify a learning signal and return the next-step recommendation."""

        history = self._bounded_history(signal.recent_performance)
        average = fmean(history)
        variance = fmean((value - average) ** 2 for value in history)
        consistency = self._clamp(1.0 - variance)
        struggle = self._struggle_score(
            average,
            signal.time_on_task,
            signal.errors_made,
            signal.hints_used,
        )
        zone = self._zone(average, struggle)
        low, high, sweet_spot = self._difficulty_window(signal.current_mastery, zone)
        result = ZPDResult(
            zone=zone,
            average_performance=round(average, 3),
            performance_consistency=round(consistency, 3),
            struggle_score=struggle,
            optimal_min=low,
            optimal_max=high,
            sweet_spot=sweet_spot,
            recommendation=self._ZONE_RECOMMENDATIONS[zone],
        )
        self._analyses += 1
        if self._bus:
            self._bus.emit(
                "acquired.learning.zpd",
                {
                    "zone": result.zone.value,
                    "recommendation": result.recommendation,
                    "sweet_spot": result.sweet_spot,
                    "struggle_score": result.struggle_score,
                },
            )
        return result

    def scaffolding(
        self,
        topic: str,
        performance: float,
        error_patterns: Iterable[str] = (),
    ) -> Dict[str, Any]:
        """Generate a bounded scaffold plan for a learner and topic."""

        score = self._clamp(performance)
        patterns = {str(pattern).strip().lower() for pattern in error_patterns}
        if score < 0.40:
            intensity, limit = "heavy", 4
        elif score < 0.60:
            intensity, limit = "medium", 3
        elif score < 0.80:
            intensity, limit = "light", 2
        else:
            intensity, limit = "minimal", 1

        candidates: List[Scaffold] = []
        if "conceptual" in patterns:
            candidates.append(
                Scaffold(
                    ScaffoldType.ANALOGY,
                    1,
                    "before_attempt",
                    f"Connect {topic} to a familiar system, then map each part explicitly.",
                )
            )
        if "procedural" in patterns:
            candidates.append(
                Scaffold(
                    ScaffoldType.STEP_BY_STEP,
                    2,
                    "on_first_error",
                    "Identify inputs, define the target, choose an approach, execute, then verify.",
                )
            )
        if "application" in patterns:
            candidates.append(
                Scaffold(
                    ScaffoldType.WORKED_EXAMPLE,
                    3,
                    "after_second_error",
                    f"Work one analogous {topic} problem end-to-end before retrying the target.",
                )
            )

        # Always retain a progressive hint path.  Insert it first when no
        # specific error pattern exists so minimal plans remain useful.
        hint = Scaffold(
            ScaffoldType.HINT,
            4,
            "on_request",
            f"Expose one clue at a time for {topic}; stop as soon as the learner can continue.",
        )
        if candidates:
            candidates.append(hint)
        else:
            candidates.insert(0, hint)

        plan = [item.to_dict() for item in candidates[:limit]]
        if self._bus:
            self._bus.emit(
                "acquired.learning.scaffolding",
                {"topic": topic, "intensity": intensity, "count": len(plan)},
            )
        return {
            "scaffolding_intensity": intensity,
            "scaffolds": plan,
            "total_available": len(candidates),
            "fading_strategy": "reduce support after sustained independent success",
        }

    def stats(self) -> Dict[str, int]:
        return {"analyses": self._analyses}


class ProgressionTracker:
    """Safe XP and mastery progression calculations.

    Levels are one-based for XP thresholds, with level 0 as the starting state.
    Unlike the original finite table this implementation works for any
    non-negative level while still using the same 1.5x growth curve.
    """

    @staticmethod
    def xp_threshold(level: int) -> int:
        level = max(0, int(level))
        if level == 0:
            return 0
        return int(100 * (1.5 ** (level - 1)))

    @classmethod
    def level_for_xp(cls, total_xp: int, max_level: int = 100) -> int:
        xp = max(0, int(total_xp))
        level = 0
        while level < max_level and xp >= cls.xp_threshold(level + 1):
            level += 1
        return level

    @classmethod
    def summarize(
        cls,
        total_xp: int,
        completed_lessons: Sequence[Dict[str, Any]] = (),
        current_level: Optional[int] = None,
    ) -> Dict[str, Any]:
        xp = max(0, int(total_xp))
        level = cls.level_for_xp(xp) if current_level is None else max(0, int(current_level))
        current_floor = cls.xp_threshold(level)
        next_floor = cls.xp_threshold(level + 1)
        span = max(1, next_floor - current_floor)
        progress = cls._clamp01((xp - current_floor) / span)

        total = len(completed_lessons)
        mastered = sum(1 for lesson in completed_lessons if float(lesson.get("mastery", 0.0)) >= 0.90)
        recent = list(completed_lessons[-7:])
        avg_seconds = (
            sum(max(0, int(lesson.get("time_spent", 0))) for lesson in recent) / len(recent)
            if recent
            else 0.0
        )
        return {
            "current_level": level,
            "total_xp": xp,
            "level_progress": round(progress, 3),
            "xp_to_next_level": max(0, next_floor - xp),
            "stats": {
                "total_lessons_completed": total,
                "lessons_mastered": mastered,
                "mastery_rate": round(mastered / max(total, 1), 3),
                "avg_time_per_lesson_minutes": round(avg_seconds / 60.0, 2),
                "learning_velocity": round(len(recent) / 7.0, 3),
            },
        }

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))


__all__ = [
    "AdaptiveLearningEngine",
    "DifficultyZone",
    "LearningSignal",
    "ProgressionTracker",
    "Scaffold",
    "ScaffoldType",
    "ZPDResult",
]
