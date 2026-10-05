"""Curriculum sequencing for Jeeves — lessons with prerequisite graphs.

The tutor can't just teach whatever; average order matters. A Curriculum
is a DAG of lessons; sequencing gates on mastery from the assessment
engine so a student only sees what they're ready for.

- :class:`Lesson` — id, prerequisites, Bloom target
- :class:`Curriculum` — topological browse, mastery-gated next lesson
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from skeleton.kernel.errors import KernelError
from skeleton.jeeves.assessment import AssessmentEngine, BloomLevel


class CurriculumError(KernelError):
    code = "JEE.CURRICULUM"


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    title: str
    skill_id: str
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND
    prerequisites: Tuple[str, ...] = ()
    mastery_gate: float = 0.6  # required mastery of prerequisites


class Curriculum:
    """Ordered lesson graph gated by assessment mastery."""

    def __init__(self) -> None:
        self._lessons: Dict[str, Lesson] = {}

    def add(self, lesson: Lesson) -> None:
        if lesson.lesson_id in self._lessons:
            raise CurriculumError(
                "duplicate lesson", context={"lesson": lesson.lesson_id}
            )
        for prereq in lesson.prerequisites:
            if prereq not in self._lessons:
                raise CurriculumError(
                    "unknown prerequisite",
                    context={"lesson": lesson.lesson_id, "prereq": prereq},
                )
        self._lessons[lesson.lesson_id] = lesson

    def sequence(self) -> Tuple[Lesson, ...]:
        """Topological ordering; raises on cycles."""
        order: List[Lesson] = []
        visited: set = set()
        temp: set = set()

        def visit(lid: str) -> None:
            if lid in temp:
                raise CurriculumError(
                    "prerequisite cycle", context={"at": lid}
                )
            if lid in visited:
                return
            temp.add(lid)
            for prereq in self._lessons[lid].prerequisites:
                visit(prereq)
            temp.discard(lid)
            visited.add(lid)
            order.append(self._lessons[lid])

        for lid in list(self._lessons):
            visit(lid)
        return tuple(order)

    def ready(
        self, engine: AssessmentEngine
    ) -> Tuple[Lesson, ...]:
        """Lessons whose prerequisites all clear their mastery gates."""
        out: List[Lesson] = []
        for lesson in self._lessons.values():
            prereqs_ok = all(
                engine._skills.get(p) is not None
                and engine._skills[p].mastery >= lesson.mastery_gate
                for p in lesson.prerequisites
            )
            if prereqs_ok:
                out.append(lesson)
        return tuple(out)

    def next_for(self, engine: AssessmentEngine) -> Optional[Lesson]:
        """Lowest-position sequenced lesson that's currently ready."""
        ready_ids = {l.lesson_id for l in self.ready(engine)}
        for lesson in self.sequence():
            if lesson.lesson_id in ready_ids:
                return lesson
        return None
