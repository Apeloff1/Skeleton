"""Grand Jeeves control plane.

This is Skeleton's provider-neutral integration layer for curriculum, memory,
learning control, energy, progression, and evidence capture. It is designed to
become the decision core underneath model/tool/storage adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from skeleton.school.curriculum import CurriculumGraph, LearningRecommendation, rank_recommendations
from skeleton.school.energy import EnergyBudget, EnergyDecision, choose_energy_strategy
from skeleton.school.learning_control import LearningControl, LearningControlDecision, LearningState
from skeleton.school.memory import LearnerMemory, MemoryMatch, MemoryStore
from skeleton.school.outcomes import OutcomeResult, SessionOutcome, apply_outcome
from skeleton.school.progression import ProgressionSnapshot, evaluate_progression
from skeleton.school.reflection import ReflectionJournal
from skeleton.school.student import StudentProfile


@dataclass(frozen=True)
class JeevesDecision:
    domain: str
    decision: str
    rationale: tuple[str, ...]
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class JeevesSessionPlan:
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
    curriculum: CurriculumGraph
    memory: MemoryStore = field(default_factory=MemoryStore)
    reflections: ReflectionJournal = field(default_factory=ReflectionJournal)
    learning_control: LearningControl = field(default_factory=LearningControl)

    def __post_init__(self) -> None:
        self.curriculum.validate()

    def plan(self, student: StudentProfile, *, query_terms: Sequence[str] = (), learning_state: LearningState | None = None, energy_budget: EnergyBudget | None = None, max_results: int = 3) -> JeevesSessionPlan:
        recommendations = tuple(rank_recommendations(self.curriculum, {skill_id: state.mastery for skill_id, state in student.skills.items()}, goals=student.goals, interests=student.interests, max_results=max_results))
        primary = recommendations[0].skill_id if recommendations else None
        skills = (primary,) if primary else ()
        memories = tuple(self.memory.retrieve(query_terms=query_terms, skill_ids=skills, limit=5))
        due = tuple(self.memory.retention_due())
        state = learning_state or self._derive_learning_state(student, primary)
        control = self.learning_control.decide(state)
        budget = energy_budget or EnergyBudget(current=student.energy)
        energy = choose_energy_strategy(budget, requested_minutes=recommendations[0].estimated_minutes if recommendations else 30, high_cognitive_load=state.cognitive_load > 0.8)
        progression = evaluate_progression(evidence={
            "successful_attempts": float(sum(skill.successes for skill in student.skills.values())),
            "independent_solutions": float(student.facts.get("independent_solutions", "0")),
            "transfer_tasks": float(student.facts.get("transfer_tasks", "0")),
            "quality_reflections": float(len(self.reflections.entries)),
            "misconceptions_repaired": float(student.facts.get("misconceptions_repaired", "0")),
            "projects_completed": float(student.facts.get("projects_completed", "0")),
        })
        decisions = (
            JeevesDecision("curriculum", primary or "review_memory", tuple(r.reason for r in recommendations[:2]) or ("No prerequisite-ready skill; use retrieval/reflection.",)),
            JeevesDecision("learning_control", control.difficulty_adjustment, control.rationale or ("Maintain current trajectory.",)),
            JeevesDecision("memory", "retrieve" if memories else "build_memory", tuple(m.reason for m in memories[:2]) or ("No retained match; create new evidence.",)),
            JeevesDecision("retention", "review_due_memory" if due else "continue_schedule", (f"{len(due)} memories are below retention threshold.",)),
            JeevesDecision("energy", energy.strategy.value, energy.rationale),
        )
        evidence = ["response quality or solution score", "learner explanation / reasoning quality", "independence or scaffold required"]
        if primary:
            evidence.append(f"evidence for skill:{primary}")
        if control.practice_schedule == "increase_spaced_repetition":
            evidence.append("retrieval result after delayed review")
        if due:
            evidence.append("retention outcome for due memory")
        return JeevesSessionPlan(recommendations, primary, memories, due, control, energy, progression, decisions, max(5, energy.session_minutes), tuple(dict.fromkeys(evidence)))

    def record_outcome(self, student: StudentProfile, outcome: SessionOutcome, *, previous_unlocked: frozenset[str] = frozenset()) -> OutcomeResult:
        """Close the loop: write evidence into learner state and memory."""
        return apply_outcome(student, outcome, memory=self.memory, reflections=self.reflections, previous_unlocked=previous_unlocked)

    @staticmethod
    def _derive_learning_state(student: StudentProfile, primary_skill: str | None) -> LearningState:
        skill = student.skill(primary_skill) if primary_skill else None
        mastery = skill.mastery if skill else 0.5
        confidence = skill.confidence if skill else 0.5
        acquisition = skill.last_score if skill and skill.attempts else mastery
        return LearningState(mastery=mastery, acquisition_rate=acquisition, retention_rate=max(0.0, min(1.0, 0.5 * mastery + 0.5 * confidence)), transfer_rate=confidence, depth_score=mastery, cognitive_load=max(0.0, min(1.0, 1.0 - student.energy)), time_since_review_hours=24.0 if skill and skill.last_seen_step else 0.0, response_time_ratio=1.0)
