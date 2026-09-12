"""Closed-loop session outcome semantics for Jeeves."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4
from skeleton.school.memory import LearnerMemory, MemoryKind, MemoryStore
from skeleton.school.progression import ProgressionSnapshot, evaluate_progression
from skeleton.school.reflection import ReflectionEntry, ReflectionImportance, ReflectionJournal, ReflectionKind
from skeleton.school.student import StudentProfile


class OutcomeKind(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    MISCONCEPTION = "misconception"
    MISCONCEPTION_REPAIRED = "misconception_repaired"
    TRANSFER = "transfer"
    INDEPENDENT = "independent"
    PROJECT = "project"


@dataclass(frozen=True)
class SessionOutcome:
    skill_id: str
    score: float
    confidence: float | None = None
    minutes: float = 0.0
    step: int = 0
    kind: OutcomeKind = OutcomeKind.SUCCESS
    summary: str = ""
    learner_explanation: str = ""
    misconception: str | None = None
    lesson_learned: str | None = None


@dataclass(frozen=True)
class OutcomeResult:
    skill_mastery: float
    progression: ProgressionSnapshot
    memory_key: str
    reflection_id: str
    signals: tuple[str, ...]


def apply_outcome(
    student: StudentProfile,
    outcome: SessionOutcome,
    *,
    memory: MemoryStore,
    reflections: ReflectionJournal,
    previous_unlocked: frozenset[str] = frozenset(),
) -> OutcomeResult:
    score = max(0.0, min(1.0, outcome.score))
    text = outcome.summary or outcome.learner_explanation or outcome.kind.value
    # Mutate through the public learner API, then resolve the canonical state
    # from the profile.  This keeps the outcome engine robust to lightweight
    # learner adapters that implement record_evidence for side effects without
    # returning the updated SkillState object.
    student.record_evidence(
        outcome.skill_id,
        score,
        confidence=outcome.confidence,
        minutes=outcome.minutes,
        step=outcome.step,
        evidence=text,
    )
    state = student.skill(outcome.skill_id)
    kind = (
        MemoryKind.MISCONCEPTION
        if outcome.kind is OutcomeKind.MISCONCEPTION
        else MemoryKind.PROCEDURAL
        if outcome.kind in {
            OutcomeKind.SUCCESS,
            OutcomeKind.INDEPENDENT,
            OutcomeKind.TRANSFER,
            OutcomeKind.MISCONCEPTION_REPAIRED,
        }
        else MemoryKind.EPISODIC
    )
    memory_key = f"session-{uuid4().hex}"
    memory.remember(
        LearnerMemory(
            key=memory_key,
            content=text,
            kind=kind,
            skill_ids=(outcome.skill_id,),
            importance=max(0.1, score),
            confidence=max(0.0, min(1.0, outcome.confidence if outcome.confidence is not None else score)),
        )
    )
    if outcome.misconception:
        memory.remember(
            LearnerMemory(
                key=f"misconception-{uuid4().hex}",
                content=outcome.misconception,
                kind=MemoryKind.MISCONCEPTION,
                skill_ids=(outcome.skill_id,),
                importance=0.9,
                confidence=0.9,
            )
        )
    reflection_kind = {
        OutcomeKind.SUCCESS: ReflectionKind.SUCCESS,
        OutcomeKind.FAILURE: ReflectionKind.FAILURE,
        OutcomeKind.MISCONCEPTION: ReflectionKind.MISCONCEPTION,
        OutcomeKind.MISCONCEPTION_REPAIRED: ReflectionKind.INSIGHT,
        OutcomeKind.TRANSFER: ReflectionKind.INSIGHT,
        OutcomeKind.INDEPENDENT: ReflectionKind.MILESTONE,
        OutcomeKind.PROJECT: ReflectionKind.MILESTONE,
    }[outcome.kind]
    reflection_id = f"reflection-{uuid4().hex}"
    reflections.record(
        ReflectionEntry(
            entry_id=reflection_id,
            kind=reflection_kind,
            title=f"{outcome.skill_id}: {outcome.kind.value}",
            content=text,
            importance=(ReflectionImportance.MILESTONE if outcome.kind in {OutcomeKind.INDEPENDENT, OutcomeKind.PROJECT} else ReflectionImportance.NORMAL),
            skills=(outcome.skill_id,),
            lesson_learned=outcome.lesson_learned,
        )
    )
    evidence = {
        "successful_attempts": float(state.successes),
        "independent_solutions": float(outcome.kind is OutcomeKind.INDEPENDENT),
        "transfer_tasks": float(outcome.kind is OutcomeKind.TRANSFER),
        "quality_reflections": float(len(reflections.entries)),
        "misconceptions_repaired": float(outcome.kind is OutcomeKind.MISCONCEPTION_REPAIRED and score >= 0.7),
        "projects_completed": float(outcome.kind is OutcomeKind.PROJECT),
    }
    progression = evaluate_progression(evidence=evidence, already_unlocked=previous_unlocked)
    signals = ["evidence_recorded", "memory_updated", "reflection_recorded"]
    if progression.newly_unlocked:
        signals.append("achievement_unlocked")
    if outcome.kind is OutcomeKind.MISCONCEPTION:
        signals.append("misconception_requires_follow_up")
    if outcome.kind is OutcomeKind.MISCONCEPTION_REPAIRED:
        signals.append("misconception_repair_recorded")
    if score >= 0.85:
        signals.append("consider_challenge_or_transfer")
    elif score < 0.5:
        signals.append("consider_scaffolding_or_reteach")
    return OutcomeResult(state.mastery, progression, memory_key, reflection_id, tuple(signals))
