"""Evidence-driven progression policies mined from Newfix achievements.

Game achievements become school milestones when rewards are treated as feedback
rather than currency: a learner demonstrates observable evidence, crosses a
threshold, and receives a meaningful next-goal signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AchievementRequirement:
    achievement_id: str
    name: str
    metric: str
    threshold: float
    category: str = "progression"
    hidden: bool = False


@dataclass(frozen=True)
class AchievementEvidence:
    metric: str
    value: float
    source: str = ""


@dataclass(frozen=True)
class AchievementResult:
    achievement: AchievementRequirement
    unlocked: bool
    progress: float
    remaining: float


@dataclass(frozen=True)
class ProgressionSnapshot:
    unlocked: tuple[str, ...]
    newly_unlocked: tuple[str, ...]
    next_goals: tuple[str, ...]


DEFAULT_ACHIEVEMENTS: tuple[AchievementRequirement, ...] = (
    AchievementRequirement("first_success", "First Success", "successful_attempts", 1, "mastery"),
    AchievementRequirement("consistent_success", "Consistent Success", "successful_attempts", 5, "mastery"),
    AchievementRequirement("independent_solution", "Independent Solver", "independent_solutions", 1, "transfer"),
    AchievementRequirement("transfer", "Transfer", "transfer_tasks", 1, "transfer"),
    AchievementRequirement("reflection", "Reflective Learner", "quality_reflections", 3, "metacognition"),
    AchievementRequirement("misconception_repair", "Model Repaired", "misconceptions_repaired", 1, "mastery"),
    AchievementRequirement("project_complete", "Project Finisher", "projects_completed", 1, "application"),
)


def evaluate_achievement(
    achievement: AchievementRequirement,
    evidence: AchievementEvidence | Mapping[str, float],
) -> AchievementResult:
    """Evaluate one threshold without awarding anything or mutating state."""
    if isinstance(evidence, AchievementEvidence):
        value = evidence.value if evidence.metric == achievement.metric else 0.0
    else:
        value = float(evidence.get(achievement.metric, 0.0))
    threshold = max(achievement.threshold, 1e-9)
    progress = min(1.0, max(0.0, value / threshold))
    return AchievementResult(achievement, value >= achievement.threshold, progress, max(0.0, achievement.threshold - value))


def evaluate_progression(
    achievements: tuple[AchievementRequirement, ...] = DEFAULT_ACHIEVEMENTS,
    evidence: Mapping[str, float] | None = None,
    already_unlocked: set[str] | frozenset[str] = frozenset(),
) -> ProgressionSnapshot:
    """Return newly crossed milestones and useful future goals."""
    evidence = evidence or {}
    unlocked = set(already_unlocked)
    newly: list[str] = []
    candidates: list[tuple[float, str]] = []
    for achievement in achievements:
        result = evaluate_achievement(achievement, evidence)
        if result.unlocked:
            if achievement.achievement_id not in unlocked:
                newly.append(achievement.achievement_id)
            unlocked.add(achievement.achievement_id)
        elif not achievement.hidden:
            candidates.append((result.progress, achievement.achievement_id))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return ProgressionSnapshot(tuple(sorted(unlocked)), tuple(newly), tuple(item[1] for item in candidates[:3]))


def achievement_learning_signal(result: AchievementResult) -> str:
    """Translate achievement state into a tutor-facing intervention signal."""
    if result.unlocked:
        return "celebrate_and_escalate"
    if result.progress >= 0.8:
        return "targeted_practice"
    if result.progress >= 0.5:
        return "guided_practice"
    return "build_foundation"
