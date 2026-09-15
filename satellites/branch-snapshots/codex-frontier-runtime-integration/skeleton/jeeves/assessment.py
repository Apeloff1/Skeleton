"""Assessment engine for Jeeves — the tutor's view of student competence.

Jeeves teaches. Teaching without measurement is just talking. This module
gives Jeeves a lightweight, privacy-preserving assessment layer:

- SkillModel: a single skill with mastery level (0-1) and confidence
- AssessmentEngine: updates mastery from interaction evidence
- BloomProfiler: maps interactions to Bloom's taxonomy levels
- AdaptiveTest: selects the next question based on current estimates
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import KernelError


class AssessmentError(KernelError):
    code = "JEE.ASSESSMENT"


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
        self.mastery = max(0.0, min(1.0, self.mastery))
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class InteractionEvidence:
    skill_id: str
    correct: bool
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND
    latency_s: float = 0.0
    hints_used: int = 0


class AssessmentEngine:
    """Bayesian-ish mastery update from interaction evidence."""

    def __init__(
        self,
        *,
        learning_rate: float = 0.15,
        decay_rate: float = 0.02,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.learning_rate = learning_rate
        self.decay_rate = decay_rate
        self._now = clock or time.monotonic
        self._skills: Dict[str, SkillModel] = {}

    def register(self, skill_id: str) -> SkillModel:
        if skill_id not in self._skills:
            self._skills[skill_id] = SkillModel(
                skill_id=skill_id, last_updated=self._now()
            )
        return self._skills[skill_id]

    def observe(self, evidence: InteractionEvidence) -> SkillModel:
        skill = self.register(evidence.skill_id)
        now = self._now()
        # simple decay since last update
        elapsed = now - skill.last_updated
        skill.mastery = max(0.0, skill.mastery - self.decay_rate * elapsed)

        # update based on correctness and difficulty proxy
        weight = {
            BloomLevel.REMEMBER: 0.8,
            BloomLevel.UNDERSTAND: 1.0,
            BloomLevel.APPLY: 1.2,
            BloomLevel.ANALYSE: 1.4,
            BloomLevel.EVALUATE: 1.6,
            BloomLevel.CREATE: 2.0,
        }.get(evidence.bloom_level, 1.0)

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
        skill = self._skills.get(skill_id)
        if skill is None:
            raise AssessmentError("unknown skill", context={"skill": skill_id})
        return {
            "skill": skill.skill_id,
            "mastery": round(skill.mastery, 4),
            "confidence": round(skill.confidence, 4),
            "attempts": skill.attempts,
            "idle_s": round(self._now() - skill.last_updated, 1),
        }

    def weakest(self, n: int = 3) -> Tuple[SkillModel, ...]:
        items = sorted(self._skills.values(), key=lambda s: s.mastery * s.confidence)
        return tuple(items[:n])


class AdaptiveTest:
    """Selects the next item based on current mastery estimates."""

    def __init__(self, engine: AssessmentEngine) -> None:
        self.engine = engine

    def next_skill(self) -> Optional[str]:
        weakest = self.engine.weakest(1)
        return weakest[0].skill_id if weakest else None

    def should_remediate(self, skill_id: str, threshold: float = 0.4) -> bool:
        skill = self.engine._skills.get(skill_id)
        return skill is not None and skill.mastery < threshold
