"""Evidence-driven Jeeves session orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from skeleton.school.engine import SchoolEngine
from skeleton.school.learning_control import LearningControl, LearningState
from skeleton.school.memory import MemoryKind, MemoryMatch, MemoryStore
from skeleton.school.student import StudentProfile


@dataclass(frozen=True)
class SessionDecision:
    action: str
    reason: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class JeevesSessionPlan:
    recommendations: tuple[object, ...]
    suggested_minutes: int
    learning_control: object
    memories: tuple[MemoryMatch, ...]
    decisions: tuple[SessionDecision, ...]
    focus_skill: str | None
    session_mode: str


@dataclass
class JeevesSessionEngine:
    """Compose Skeleton's learner, curriculum, memory and control policies."""

    school: SchoolEngine
    memory: MemoryStore = field(default_factory=MemoryStore)
    learning_control: LearningControl = field(default_factory=LearningControl)

    def plan(self, student: StudentProfile, *, learning_state: LearningState | None = None,
             query_terms: Sequence[str] = (), max_results: int = 3) -> JeevesSessionPlan:
        school_plan = self.school.plan(student, max_results=max_results)
        focus = school_plan.recommendations[0].skill_id if school_plan.recommendations else None
        state = learning_state or self._state_from_student(student, focus)
        control = self.learning_control.decide(state)
        memories = tuple(self.memory.retrieve(
            query_terms=query_terms, skill_ids=(focus,) if focus else (),
            kinds=(MemoryKind.MISCONCEPTION, MemoryKind.PROCEDURAL, MemoryKind.GOAL), limit=5,
        ))
        decisions: list[SessionDecision] = []
        if focus:
            decisions.append(SessionDecision("focus", "Choose the highest-ranked prerequisite-ready learning target.", (f"skill:{focus}",)))
        decisions.append(SessionDecision("control", "Learning-control policy selected the difficulty response.", tuple(control.rationale)))
        if memories:
            decisions.append(SessionDecision("retrieve_memory", "Relevant prior learner evidence should shape the next intervention.", tuple(m.memory.key for m in memories)))
        if control.retention_strategy == "scheduled_review_needed":
            decisions.append(SessionDecision("review", "Retention policy indicates a review is due."))
        return JeevesSessionPlan(tuple(school_plan.recommendations), school_plan.suggested_minutes, control,
                                 memories, tuple(decisions), focus, self._mode(student, control.content_strategy))

    @staticmethod
    def _state_from_student(student: StudentProfile, focus: str | None) -> LearningState:
        skill = student.skill(focus) if focus else None
        mastery = skill.mastery if skill else 0.5
        confidence = skill.confidence if skill else 0.5
        return LearningState(mastery=mastery, acquisition_rate=skill.last_score if skill and skill.attempts else 0.5,
                             retention_rate=confidence, transfer_rate=mastery, depth_score=mastery,
                             cognitive_load=max(0.0, min(1.0, 1.0 - student.energy)))

    @staticmethod
    def _mode(student: StudentProfile, content_strategy: str) -> str:
        if student.energy < 0.25:
            return "recovery"
        if content_strategy == "varied_contexts":
            return "transfer"
        if content_strategy == "retrieval_plus_examples":
            return "retrieval"
        return "application"
