"""School primitives for the Tutolage + Jeeves learning core."""

from skeleton.school.assessment import AssessmentEngine, AssessmentEvidence, AssessmentKind, Intervention
from skeleton.school.code_lab import CodeFinding, CodeLabEngine, CodeReview, CodeTask, FindingSeverity
from skeleton.school.curriculum import CurriculumGraph, CurriculumNode, LearningRecommendation, rank_recommendations
from skeleton.school.engine import SchoolEngine, SchoolPlan
from skeleton.school.learning_control import LearningControl, LearningControlDecision, LearningState
from skeleton.school.student import SkillState, StudentProfile

__all__ = [
    "AssessmentEngine", "AssessmentEvidence", "AssessmentKind", "Intervention",
    "CodeFinding", "CodeLabEngine", "CodeReview", "CodeTask", "FindingSeverity",
    "CurriculumGraph", "CurriculumNode", "LearningRecommendation", "rank_recommendations",
    "SchoolEngine", "SchoolPlan", "LearningControl", "LearningControlDecision", "LearningState",
    "SkillState", "StudentProfile",
]
