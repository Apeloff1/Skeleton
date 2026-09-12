"""Grand Jeeves provider-neutral school control plane."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Sequence
from skeleton.school.counterfactual import CounterfactualResult, default_candidates, compete
from skeleton.school.curriculum import CurriculumGraph, LearningRecommendation, rank_recommendations
from skeleton.school.energy import EnergyBudget, EnergyDecision, choose_energy_strategy
from skeleton.school.epistemics import EpistemicEngine
from skeleton.school.learning_control import LearningControl, LearningControlDecision, LearningState
from skeleton.school.memory import LearnerMemory, MemoryMatch, MemoryStore
from skeleton.school.outcomes import OutcomeKind, OutcomeResult, SessionOutcome, apply_outcome
from skeleton.school.policy_calibration import PolicyCalibrator
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
    policy_competition: CounterfactualResult | None = None
    policy_calibrator: PolicyCalibrator | None = None


@dataclass
class JeevesControlPlane:
    curriculum: CurriculumGraph
    memory: MemoryStore = field(default_factory=MemoryStore)
    reflections: ReflectionJournal = field(default_factory=ReflectionJournal)
    learning_control: LearningControl = field(default_factory=LearningControl)
    epistemics: EpistemicEngine = field(default_factory=EpistemicEngine)
    policy_calibrator: PolicyCalibrator = field(default_factory=PolicyCalibrator)

    def __post_init__(self) -> None:
        self.curriculum.validate()

    def plan(self, student: StudentProfile, *, query_terms: Sequence[str] = (), learning_state: LearningState | None = None, energy_budget: EnergyBudget | None = None, max_results: int = 3) -> JeevesSessionPlan:
        recommendations = tuple(rank_recommendations(self.curriculum, {k: s.mastery for k, s in student.skills.items()}, goals=student.goals, interests=student.interests, max_results=max_results))
        primary = recommendations[0].skill_id if recommendations else None
        memories = tuple(self.memory.retrieve(query_terms=query_terms, skill_ids=(primary,) if primary else (), limit=5))
        due = tuple(self.memory.retention_due())
        state = learning_state or self._derive_learning_state(student, primary)
        control = self.learning_control.decide(state)
        budget = energy_budget or EnergyBudget(current=student.energy)
        energy = choose_energy_strategy(budget, requested_minutes=recommendations[0].estimated_minutes if recommendations else 30, high_cognitive_load=state.cognitive_load > .8)
        progression = evaluate_progression(evidence={
            "successful_attempts": float(sum(s.successes for s in student.skills.values())),
            "independent_solutions": float(student.facts.get("independent_solutions", "0")),
            "transfer_tasks": float(student.facts.get("transfer_tasks", "0")),
            "quality_reflections": float(len(self.reflections.entries)),
            "misconceptions_repaired": float(student.facts.get("misconceptions_repaired", "0")),
            "projects_completed": float(student.facts.get("projects_completed", "0")),
        })
        claim = primary or (query_terms[0] if query_terms else "current objective")
        belief = self.epistemics.beliefs.get(claim)
        contradiction = 1.0 if belief and belief.contradiction else 0.0
        competition = compete(
            default_candidates(mastery=state.mastery, contradiction=contradiction, energy=student.energy, transfer_ready=state.transfer_rate >= .7 and state.mastery >= .7),
            reliability=self.policy_calibrator.snapshot(),
        )
        decisions = (
            JeevesDecision("curriculum", primary or "review_memory", tuple(r.reason for r in recommendations[:2]) or ("No prerequisite-ready skill; use retrieval/reflection.",)),
            JeevesDecision("learning_control", control.difficulty_adjustment, control.rationale or ("Maintain current trajectory.",)),
            JeevesDecision("memory", "retrieve" if memories else "build_memory", tuple(m.reason for m in memories[:2]) or ("No retained match; create new evidence.",)),
            JeevesDecision("retention", "review_due_memory" if due else "continue_schedule", (f"{len(due)} memories are below retention threshold.",)),
            JeevesDecision("energy", energy.strategy.value, energy.rationale),
            JeevesDecision("policy_competition", competition.selected.action.value, competition.rationale, tuple(c.action.value for c in competition.rejected)),
        )
        evidence = ["response quality or solution score", "learner explanation / reasoning quality", "independence or scaffold required"]
        if primary:
            evidence.append(f"evidence for skill:{primary}")
        if due:
            evidence.append("retention outcome for due memory")
        if contradiction:
            evidence.append("resolution of contradictory evidence")
        return JeevesSessionPlan(recommendations, primary, memories, due, control, energy, progression, decisions, max(5, energy.session_minutes), tuple(dict.fromkeys(evidence)), competition, self.policy_calibrator)

    def record_outcome(self, student: StudentProfile, outcome: SessionOutcome, *, previous_unlocked=frozenset(), policy_action: str | None = None) -> OutcomeResult:
        result = apply_outcome(student, outcome, memory=self.memory, reflections=self.reflections, previous_unlocked=previous_unlocked)
        if policy_action:
            reward = self._policy_reward(outcome)
            self.policy_calibrator.observe(policy_action, reward=reward, successful=reward >= .5)
        return result

    @staticmethod
    def _policy_reward(outcome: SessionOutcome) -> float:
        if outcome.kind is OutcomeKind.MISCONCEPTION:
            return -0.6
        if outcome.kind is OutcomeKind.FAILURE:
            return -0.35
        base = max(0.0, min(1.0, outcome.score))
        if outcome.kind in {OutcomeKind.INDEPENDENT, OutcomeKind.TRANSFER, OutcomeKind.PROJECT}:
            base = min(1.0, base + .15)
        return base

    @staticmethod
    def _derive_learning_state(student: StudentProfile, primary_skill: str | None) -> LearningState:
        skill = student.skill(primary_skill) if primary_skill else None
        mastery = skill.mastery if skill else .5
        confidence = skill.confidence if skill else .5
        acquisition = skill.last_score if skill and skill.attempts else mastery
        return LearningState(
            mastery=mastery,
            acquisition_rate=acquisition,
            retention_rate=max(0.0, min(1.0, .5 * mastery + .5 * confidence)),
            transfer_rate=confidence,
            depth_score=mastery,
            cognitive_load=max(0.0, min(1.0, 1.0 - student.energy)),
            time_since_review_hours=24.0 if skill and skill.last_seen_step else 0.0,
            response_time_ratio=1.0,
        )
