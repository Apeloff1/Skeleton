"""Grand Jeeves control plane.

This module is the integration layer for Skeleton's school intelligence.  It
turns independent policy primitives into a single auditable session decision:
what to teach, why now, how hard, how long, which memories matter, when to
review, and what evidence must be captured next.

The control plane is deliberately provider-neutral. Models, vector stores,
UI, databases, tools, and transport can sit above it without changing the
learning policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from skeleton.school.curriculum import CurriculumGraph, LearningRecommendation, rank_recommendations
from skeleton.school.energy import EnergyBudget, EnergyDecision, choose_energy_strategy
from skeleton.school.learning_control import LearningControl, LearningControlDecision, LearningState
from skeleton.school.memory import LearnerMemory, MemoryKind, MemoryMatch, MemoryStore
from skeleton.school.progression import ProgressionSnapshot, evaluate_progression
from skeleton.school.reflection import ReflectionJournal
from skeleton.school.student import StudentProfile


@dataclass(frozen=True)
class JeevesDecision:
    """One auditable decision emitted by the control plane."""

    domain: str
    decision: str
    rationale: tuple[str, ...]
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class JeevesSessionPlan:
    """Complete next-action plan for one learner session."""

    recommendations: tuple[LearningRecommendation, ...]
    primary_skill: str | None
    memory_matches: tuple[MemoryMatch, ...]
    retention_due: tuple[LearnerMemory, ...]
    learning_control: LearningControlDecision
    energy: EnergyDecision
    progression: ProgressionSnapshot
    decisions: tuple[JeevesDecision, ...]
    suggested_minutes: int
    next_evidence: tuple[str, ...]


@dataclass
class JeevesControlPlane:
    """Compose curriculum, memory, learning control, energy and progression."""

    curriculum: CurriculumGraph
    memory: MemoryStore = field(default_factory=MemoryStore)
    reflections: ReflectionJournal = field(default_factory=ReflectionJournal)
    learning_control: LearningControl = field(default_factory=LearningControl)

    def __post_init__(self) -> None:
        self.curriculum.validate()

    def plan(
        self,
        student: StudentProfile,
        *,
        query_terms: Sequence[str] = (),
        learning_state: LearningState | None = None,
        energy_budget: EnergyBudget | None = None,
        max_results: int = 3,
    ) -> JeevesSessionPlan:
        """Generate a full session plan from current learner evidence."""
        recommendations = tuple(
            rank_recommendations(
                self.curriculum,
                {skill_id: state.mastery for skill_id, state in student.skills.items()},
                goals=student.goals,
                interests=student.interests,
                max_results=max_results,
            )
        )
        primary = recommendations[0].skill_id if recommendations else None
        skills = (primary,) if primary else ()

        memories = tuple(
            self.memory.retrieve(
                query_terms=query_terms,
                skill_ids=skills,
                limit=5,
            )
        )
        due = tuple(self.memory.retention_due())

        if learning_state is None:
            state = self._derive_learning_state(student, primary)
        else:
            state = learning_state
        control = self.learning_control.decide(state)

        budget = energy_budget or EnergyBudget(current=student.energy)
        energy = choose_energy_strategy(budget, mastery=state.mastery, cognitive_load=state.cognitive_load)
        progression = evaluate_progression(student)

        decisions: list[JeevesDecision] = [
            JeevesDecision(
                "curriculum",
                primary or "review_memory",
                tuple(r.reason for r in recommendations[:2]) or ("No prerequisite-ready skill; use retrieval/reflection.",),
            ),
            JeevesDecision(
                "learning_control",
                control.difficulty_adjustment,
                control.rationale or ("Maintain current learning trajectory.",),
            ),
            JeevesDecision(
                "memory",
                "retrieve" if memories else "build_memory",
                tuple(m.reason for m in memories[:2]) or ("No retained match; create new evidence.",),
            ),
            JeevesDecision(
                "retention",
                "review_due_memory" if due else "continue_schedule",
                (f"{len(due)} memories are below retention threshold.",),
            ),
            JeevesDecision(
                "energy",
                energy.strategy.value,
                (energy.rationale,),
            ),
        ]

        suggested_minutes = min(
            recommendations[0].estimated_minutes if recommendations else 30,
            energy.session_minutes,
        )
        if state.cognitive_load > 0.8:
            suggested_minutes = min(suggested_minutes, 25)

        evidence = [
            "response quality or solution score",
            "learner explanation / reasoning quality",
            "independence or scaffold required",
        ]
        if primary:
            evidence.append(f"evidence for skill:{primary}")
        if control.practice_schedule == "increase_spaced_repetition":
            evidence.append("retrieval result after delayed review")
        if due:
            evidence.append("retention outcome for due memory")

        return JeevesSessionPlan(
            recommendations=recommendations,
            primary_skill=primary,
            memory_matches=memories,
            retention_due=due,
            learning_control=control,
            energy=energy,
            progression=progression,
            decisions=tuple(decisions),
            suggested_minutes=max(5, suggested_minutes),
            next_evidence=tuple(dict.fromkeys(evidence)),
        )

    @staticmethod
    def _derive_learning_state(student: StudentProfile, primary_skill: str | None) -> LearningState:
        skill = student.skill(primary_skill) if primary_skill else None
        mastery = skill.mastery if skill else 0.5
        confidence = skill.confidence if skill else 0.5
        acquisition = skill.last_score if skill and skill.attempts else mastery
        return LearningState(
            mastery=mastery,
            acquisition_rate=acquisition,
            retention_rate=max(0.0, min(1.0, 0.5 * mastery + 0.5 * confidence)),
            transfer_rate=confidence,
            depth_score=mastery,
            cognitive_load=max(0.0, min(1.0, 1.0 - student.energy)),
            time_since_review_hours=24.0 if skill and skill.last_seen_step else 0.0,
            response_time_ratio=1.0,
        )
