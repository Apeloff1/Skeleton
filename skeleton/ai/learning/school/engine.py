"""Jeeves school planner: connect learner evidence to curriculum and practice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from skeleton.school.assessment import AssessmentEngine
from skeleton.school.curriculum import CurriculumGraph, LearningRecommendation, rank_recommendations
from skeleton.school.student import StudentProfile


@dataclass(frozen=True)
class SchoolPlan:
    recommendations: List[LearningRecommendation]
    intervention: object | None
    suggested_minutes: int
    rationale: str


class SchoolEngine:
    """Small deterministic control plane that Jeeves can wrap with dialogue/model tools."""

    def __init__(self, curriculum: CurriculumGraph) -> None:
        curriculum.validate()
        self.curriculum = curriculum
        self.assessments = AssessmentEngine()

    def plan(self, student: StudentProfile, *, max_results: int = 3) -> SchoolPlan:
        mastery = {skill_id: state.mastery for skill_id, state in student.skills.items()}
        recommendations = rank_recommendations(
            self.curriculum,
            mastery,
            goals=student.goals,
            interests=student.interests,
            max_results=max_results,
        )
        intervention = None
        if recommendations:
            intervention = self.assessments.intervention_for(recommendations[0].skill_id)
        suggested_minutes = 20 if student.energy < 0.4 else 45
        if intervention is not None and getattr(intervention, "intensity", 1) >= 3:
            suggested_minutes = min(suggested_minutes, 30)
        rationale = "Prioritized prerequisite-ready skills using mastery gaps, goals and interests."
        if student.energy < 0.4:
            rationale += " Reduced session length because learner energy is low."
        return SchoolPlan(recommendations, intervention, suggested_minutes, rationale)
