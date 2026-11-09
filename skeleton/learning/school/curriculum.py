"""Prerequisite-aware curriculum planning extracted from Tutolage.

The source curriculum engine tracks course progression, prerequisites,
assessments and recommendations.  Skeleton keeps the decision layer pure and
provider/storage agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class CurriculumNode:
    skill_id: str
    title: str
    prerequisites: tuple[str, ...] = ()
    lesson_ids: tuple[str, ...] = ()
    estimated_minutes: int = 30
    tags: tuple[str, ...] = ()


@dataclass
class CurriculumGraph:
    nodes: Dict[str, CurriculumNode] = field(default_factory=dict)

    def add(self, node: CurriculumNode) -> None:
        if node.skill_id in node.prerequisites:
            raise ValueError(f"skill cannot depend on itself: {node.skill_id}")
        self.nodes[node.skill_id] = node

    def validate(self) -> None:
        for node in self.nodes.values():
            missing = [p for p in node.prerequisites if p not in self.nodes]
            if missing:
                raise ValueError(f"{node.skill_id} has missing prerequisites: {missing}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(skill_id: str) -> None:
            if skill_id in visiting:
                raise ValueError("curriculum contains a prerequisite cycle")
            if skill_id in visited:
                return
            visiting.add(skill_id)
            for prerequisite in self.nodes[skill_id].prerequisites:
                visit(prerequisite)
            visiting.remove(skill_id)
            visited.add(skill_id)

        for skill_id in self.nodes:
            visit(skill_id)

    def ready(self, mastered: Iterable[str], threshold: float = 0.7) -> List[CurriculumNode]:
        mastered_set = set(mastered)
        return [
            node
            for node in self.nodes.values()
            if node.skill_id not in mastered_set and all(p in mastered_set for p in node.prerequisites)
        ]


@dataclass(frozen=True)
class LearningRecommendation:
    skill_id: str
    title: str
    reason: str
    priority: float
    estimated_minutes: int


def rank_recommendations(
    graph: CurriculumGraph,
    mastery: Dict[str, float],
    *,
    goals: Sequence[str] = (),
    interests: Sequence[str] = (),
    max_results: int = 5,
) -> List[LearningRecommendation]:
    """Rank next skills using readiness, weakness, goals and learner interests."""
    mastered = {skill for skill, score in mastery.items() if score >= 0.7}
    goal_set = set(goals)
    interest_set = set(interests)
    candidates = graph.ready(mastered)
    scored: List[LearningRecommendation] = []
    for node in candidates:
        current = max(0.0, min(1.0, mastery.get(node.skill_id, 0.0)))
        gap = 1.0 - current
        goal_bonus = 0.25 if node.skill_id in goal_set else 0.0
        interest_bonus = 0.15 if interest_set.intersection(node.tags) else 0.0
        prereq_bonus = min(0.15, 0.05 * len(node.prerequisites))
        priority = gap * 0.6 + goal_bonus + interest_bonus + prereq_bonus
        reason_parts = ["next prerequisite-ready skill"]
        if current > 0:
            reason_parts.append("targets a known learning gap")
        if node.skill_id in goal_set:
            reason_parts.append("supports a stated goal")
        if interest_set.intersection(node.tags):
            reason_parts.append("matches an interest")
        scored.append(
            LearningRecommendation(
                skill_id=node.skill_id,
                title=node.title,
                reason="; ".join(reason_parts),
                priority=priority,
                estimated_minutes=node.estimated_minutes,
            )
        )
    return sorted(scored, key=lambda item: (-item.priority, item.estimated_minutes, item.skill_id))[:max_results]
