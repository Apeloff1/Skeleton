"""Session reflection for Jeeves — summarize what happened and what's next.

Assessment tells mastery; reflection narrates it. The builder assembles
a structured report the tutor presents back: attempts, Bloom coverage,
next challenges, and an encouragement scaffold note.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.jeeves.assessment import BloomLevel, InteractionEvidence, SkillModel


@dataclass(frozen=True)
class ReflectionPoint:
    kind: str
    text: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReflectionReport:
    session_id: str
    attempts: int = 0
    bloom_levels: Tuple[BloomLevel, ...] = ()
    points: List[ReflectionPoint] = field(default_factory=list)

    def add(self, kind: str, text: str, **payload: Any) -> None:
        self.points.append(ReflectionPoint(kind=kind, text=text, payload=payload))


class ReflectionBuilder:
    """Compose a report from evidence + skill snapshots."""

    def build(
        self,
        session_id: str,
        evidences: Tuple[InteractionEvidence, ...],
        skills: Tuple[SkillModel, ...],
    ) -> ReflectionReport:
        report = ReflectionReport(session_id=session_id)
        report.attempts = len(evidences)
        levels = tuple(sorted({e.bloom_level for e in evidences}))
        report.bloom_levels = levels
        for skill in skills:
            report.add(
                "skill",
                f"{skill.skill_id}: mastery {skill.mastery:.2f} conf {skill.confidence:.2f}",
                skill=skill.skill_id,
                mastery=round(skill.mastery, 4),
            )
        if evidences:
            correct = sum(1 for e in evidences if e.correct)
            report.add(
                "summary",
                f"{correct}/{len(evidences)} correct",
                correct=correct,
                total=len(evidences),
            )
        return report
