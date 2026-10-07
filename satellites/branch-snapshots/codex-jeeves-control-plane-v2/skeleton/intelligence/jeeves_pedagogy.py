"""Portable Jeeves pedagogy primitives distilled from Tutolage/Interesting-22.

This module keeps the learning policy independent of FastAPI, databases, and model
providers so it can be composed with Skeleton's intelligence layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class AssessmentKind(str, Enum):
    FORMATIVE = "formative"
    DIAGNOSTIC = "diagnostic"
    SUMMATIVE = "summative"


class ScaffoldLevel(str, Enum):
    HEAVY = "heavy"
    MODERATE = "moderate"
    LIGHT = "light"
    MINIMAL = "minimal"


@dataclass(frozen=True)
class RetrievalReview:
    interval_days: int
    purpose: str


@dataclass(frozen=True)
class LearningSession:
    stage: str
    topic: str
    structure: str
    minutes: int
    scaffold: ScaffoldLevel
    difficulty_delta: float
    include_break: bool


RETRIEVAL_SCHEDULE: tuple[RetrievalReview, ...] = (
    RetrievalReview(0, "immediate retrieval after first learning"),
    RetrievalReview(1, "first spaced review"),
    RetrievalReview(3, "second spaced review"),
    RetrievalReview(7, "one-week consolidation"),
    RetrievalReview(14, "two-week consolidation"),
    RetrievalReview(30, "monthly maintenance"),
)

SOCRATIC_QUESTION_TYPES: tuple[str, ...] = (
    "clarify",
    "probe_assumptions",
    "probe_reasons",
    "question_viewpoint",
    "probe_implications",
    "question_the_question",
)

WORKED_EXAMPLE_FADING: tuple[str, ...] = (
    "full_example",
    "partial_example",
    "solution_outline",
    "problem_only",
    "problem_identification",
)


def retrieval_schedule(max_days: int = 30) -> tuple[RetrievalReview, ...]:
    """Return spaced-retrieval checkpoints up to ``max_days``."""
    if max_days < 0:
        raise ValueError("max_days must be non-negative")
    return tuple(item for item in RETRIEVAL_SCHEDULE if item.interval_days <= max_days)


def assessment_strategy(kind: AssessmentKind) -> tuple[str, ...]:
    """Return portable evidence types for a learning assessment."""
    strategies = {
        AssessmentKind.FORMATIVE: (
            "quick_concept_check",
            "explain_the_code",
            "guided_problem",
            "self_assessment",
        ),
        AssessmentKind.DIAGNOSTIC: (
            "targeted_question",
            "error_analysis",
            "concept_map",
            "transfer_task",
        ),
        AssessmentKind.SUMMATIVE: (
            "project",
            "complex_problem",
            "teach_back",
            "real_world_application",
        ),
    }
    return strategies[kind]


def next_scaffold(current: ScaffoldLevel, *, demonstrated_mastery: bool) -> ScaffoldLevel:
    """Fade support after demonstrated mastery; increase it after a miss."""
    levels = list(ScaffoldLevel)
    index = levels.index(current)
    if demonstrated_mastery:
        return levels[min(index + 1, len(levels) - 1)]
    return levels[max(index - 1, 0)]


def choose_session_structure(minutes: int, energy_level: str = "normal") -> str:
    """Choose a compact session shape without tying the policy to a UI."""
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    if minutes < 20:
        return "quick_review"
    if minutes < 45:
        return "learn_practice_reflect"
    if energy_level == "low":
        return "review_guided_practice_break"
    if energy_level == "high":
        return "challenge_project_reflect"
    return "learn_practice_challenge_reflect"


def build_session(
    *,
    stage: str,
    topic: str,
    minutes: int,
    energy_level: str = "normal",
    difficulty: float = 0.5,
) -> LearningSession:
    """Create an adaptive session from stage, time, energy, and difficulty."""
    if not 0.0 <= difficulty <= 1.0:
        raise ValueError("difficulty must be between 0 and 1")
    if minutes <= 0:
        raise ValueError("minutes must be positive")

    scaffold_by_stage = {
        "onboarding": ScaffoldLevel.HEAVY,
        "foundation": ScaffoldLevel.MODERATE,
        "growth": ScaffoldLevel.LIGHT,
        "mastery": ScaffoldLevel.MINIMAL,
    }
    scaffold = scaffold_by_stage.get(stage, ScaffoldLevel.MODERATE)
    energy = energy_level.lower()
    delta = {"low": -0.15, "normal": 0.0, "high": 0.10}.get(energy, 0.0)
    structure = choose_session_structure(minutes, energy)
    return LearningSession(
        stage=stage,
        topic=topic,
        structure=structure,
        minutes=minutes,
        scaffold=scaffold,
        difficulty_delta=max(-0.2, min(0.2, delta)),
        include_break=minutes >= 45 and energy != "high",
    )


def interleave_topics(topics: Sequence[str]) -> tuple[str, ...]:
    """Deduplicate topics while preserving order for mixed-skill practice."""
    seen: set[str] = set()
    result: list[str] = []
    for topic in topics:
        normalized = topic.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)
