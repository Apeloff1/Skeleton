"""Assessment engine for Jeeves — the tutor's view of student competence.

Jeeves teaches. Teaching without measurement is just talking. This module
gives Jeeves a lightweight, privacy-preserving assessment layer:

- SkillModel: a single skill with mastery level (0-1) and confidence
- AssessmentEngine: updates mastery from interaction evidence
- BloomProfiler: maps interactions to Bloom's taxonomy levels
- AdaptiveTest: selects the next question based on current estimates
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from skeleton.kernel.errors import KernelError

MAX_SKILLS = 10_000
MAX_SKILL_ID_CHARS = 256
MAX_HINTS_PER_ATTEMPT = 1_000


class AssessmentError(KernelError):
    code = "JEE.ASSESSMENT"


def _finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssessmentError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise AssessmentError(f"{name} must be finite")
    return number


def _unit_interval(name: str, value: Any) -> float:
    number = _finite_number(name, value)
    if not 0.0 <= number <= 1.0:
        raise AssessmentError(f"{name} must be between 0 and 1")
    return number


def _skill_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssessmentError("skill_id must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > MAX_SKILL_ID_CHARS:
        raise AssessmentError(
            "skill_id is too long",
            context={"max_chars": MAX_SKILL_ID_CHARS},
        )
    return normalized


class BloomLevel(str, Enum):
    REMEMBER = "REMEMBER"
    UNDERSTAND = "UNDERSTAND"
    APPLY = "APPLY"
    ANALYSE = "ANALYSE"
    EVALUATE = "EVALUATE"
    CREATE = "CREATE"


@dataclass
class SkillModel:
    skill_id: str
    mastery: float = 0.0  # 0..1
    confidence: float = 0.5  # 0..1
    attempts: int = 0
    last_updated: float = 0.0

    def __post_init__(self) -> None:
        self.skill_id = _skill_id(self.skill_id)
        mastery = _finite_number("mastery", self.mastery)
        confidence = _finite_number("confidence", self.confidence)
        self.mastery = max(0.0, min(1.0, mastery))
        self.confidence = max(0.0, min(1.0, confidence))
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int) or self.attempts < 0:
            raise AssessmentError("attempts must be a non-negative integer")
        self.last_updated = _finite_number("last_updated", self.last_updated)


@dataclass
class InteractionEvidence:
    skill_id: str
    correct: bool
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND
    latency_s: float = 0.0
    hints_used: int = 0

    def __post_init__(self) -> None:
        self.skill_id = _skill_id(self.skill_id)
        if not isinstance(self.correct, bool):
            raise AssessmentError("correct must be boolean")
        if not isinstance(self.bloom_level, BloomLevel):
            try:
                self.bloom_level = BloomLevel(self.bloom_level)
            except (TypeError, ValueError) as exc:
                raise AssessmentError("unknown Bloom level") from exc
        latency = _finite_number("latency_s", self.latency_s)
        if latency < 0:
            raise AssessmentError("latency_s must be non-negative")
        self.latency_s = latency
        if (
            isinstance(self.hints_used, bool)
            or not isinstance(self.hints_used, int)
            or not 0 <= self.hints_used <= MAX_HINTS_PER_ATTEMPT
        ):
            raise AssessmentError(
                "hints_used is outside the accepted range",
                context={"max_hints": MAX_HINTS_PER_ATTEMPT},
            )


class AssessmentEngine:
    """Bayesian-ish mastery update from validated interaction evidence."""

    def __init__(
        self,
        *,
        learning_rate: float = 0.15,
        decay_rate: float = 0.02,
        clock: Optional[Callable[[], float]] = None,
        max_skills: int = MAX_SKILLS,
    ) -> None:
        self.learning_rate = _unit_interval("learning_rate", learning_rate)
        self.decay_rate = _unit_interval("decay_rate", decay_rate)
        if isinstance(max_skills, bool) or not isinstance(max_skills, int) or max_skills < 1:
            raise AssessmentError("max_skills must be a positive integer")
        if clock is not None and not callable(clock):
            raise AssessmentError("clock must be callable")
        self._max_skills = max_skills
        self._now = clock or time.monotonic
        self._skills: Dict[str, SkillModel] = {}

    def _time(self) -> float:
        return _finite_number("clock value", self._now())

    def register(self, skill_id: str) -> SkillModel:
        skill_id = _skill_id(skill_id)
        existing = self._skills.get(skill_id)
        if existing is not None:
            return existing
        if len(self._skills) >= self._max_skills:
            raise AssessmentError("skill capacity reached",
                                  context={"max_skills": self._max_skills})
        skill = SkillModel(skill_id=skill_id, last_updated=self._time())
        self._skills[skill_id] = skill
        return skill

    def mastery(self, skill_id: str) -> Optional[float]:
        """Return current stored mastery for a skill, or ``None`` if unknown.

        This is intentionally a read-only public lookup so curriculum and
        higher-level learning services do not need to reach into ``_skills``.
        It preserves the engine's existing semantics: decay is applied when
        new evidence is observed, not merely because a caller reads state.
        """
        skill_id = _skill_id(skill_id)
        skill = self._skills.get(skill_id)
        return None if skill is None else skill.mastery

    def observe(self, evidence: InteractionEvidence) -> SkillModel:
        if not isinstance(evidence, InteractionEvidence):
            raise AssessmentError("evidence must be InteractionEvidence")

        # First observation must be one atomic mutation. Historically observe()
        # delegated to register(), which sampled the clock once while creating a
        # skill and then sampled it again before applying evidence. A failure on
        # that second read left a zero-attempt skill behind. Validate capacity,
        # sample time once, then publish a new skill only after those operations
        # have succeeded.
        skill = self._skills.get(evidence.skill_id)
        if skill is None and len(self._skills) >= self._max_skills:
            raise AssessmentError(
                "skill capacity reached",
                context={"max_skills": self._max_skills},
            )
        now = self._time()
        if skill is None:
            skill = SkillModel(skill_id=evidence.skill_id, last_updated=now)
            self._skills[evidence.skill_id] = skill

        # A custom or suspended clock can move backwards. Never turn that into
        # negative decay (which would incorrectly increase mastery).
        elapsed = max(0.0, now - skill.last_updated)
        skill.mastery = max(0.0, skill.mastery - self.decay_rate * elapsed)

        weight = {
            BloomLevel.REMEMBER: 0.8,
            BloomLevel.UNDERSTAND: 1.0,
            BloomLevel.APPLY: 1.2,
            BloomLevel.ANALYSE: 1.4,
            BloomLevel.EVALUATE: 1.6,
            BloomLevel.CREATE: 2.0,
        }[evidence.bloom_level]

        penalty = 1.0 + evidence.hints_used * 0.3
        delta = self.learning_rate * weight / penalty
        if evidence.correct:
            skill.mastery = min(1.0, skill.mastery + delta * (1.0 - skill.mastery))
        else:
            skill.mastery = max(0.0, skill.mastery - delta * skill.mastery)

        skill.attempts += 1
        skill.confidence = min(1.0, skill.confidence + 0.05)
        skill.last_updated = now
        return skill

    def report(self, skill_id: str) -> Dict[str, Any]:
        skill_id = _skill_id(skill_id)
        skill = self._skills.get(skill_id)
        if skill is None:
            raise AssessmentError("unknown skill", context={"skill": skill_id})
        idle = max(0.0, self._time() - skill.last_updated)
        return {
            "skill": skill.skill_id,
            "mastery": round(skill.mastery, 4),
            "confidence": round(skill.confidence, 4),
            "attempts": skill.attempts,
            "idle_s": round(idle, 1),
        }

    def weakest(self, n: int = 3) -> Tuple[SkillModel, ...]:
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise AssessmentError("n must be a non-negative integer")
        items = sorted(
            self._skills.values(),
            key=lambda s: (s.mastery * s.confidence, s.skill_id),
        )
        return tuple(items[:n])


class AdaptiveTest:
    """Selects the next item based on current mastery estimates."""

    def __init__(self, engine: AssessmentEngine) -> None:
        if not isinstance(engine, AssessmentEngine):
            raise AssessmentError("engine must be AssessmentEngine")
        self.engine = engine

    def next_skill(self) -> Optional[str]:
        weakest = self.engine.weakest(1)
        return weakest[0].skill_id if weakest else None

    def should_remediate(self, skill_id: str, threshold: float = 0.4) -> bool:
        threshold = _unit_interval("threshold", threshold)
        mastery = self.engine.mastery(skill_id)
        return mastery is not None and mastery < threshold
