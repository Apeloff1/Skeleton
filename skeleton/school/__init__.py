"""School primitives for the Tutolage + Jeeves learning core."""

from skeleton.school.assessment import AssessmentEngine, AssessmentEvidence, AssessmentKind, Intervention
from skeleton.school.code_lab import CodeFinding, CodeLabEngine, CodeReview, CodeTask, FindingSeverity
from skeleton.school.cocoding import CodingPhase, CoCodingAction, CoCodingContext, HandoffStage, InteractionPattern, choose_action, next_handoff
from skeleton.school.curriculum import CurriculumGraph, CurriculumNode, LearningRecommendation, rank_recommendations
from skeleton.school.engine import SchoolEngine, SchoolPlan
from skeleton.school.learning_control import LearningControl, LearningControlDecision, LearningState
from skeleton.school.memory import LearnerMemory, MemoryKind, MemoryMatch, MemoryStore
from skeleton.school.prompting import PromptRefinement, RefinementNeed, refine_prompt
from skeleton.school.student import SkillState, StudentProfile

__all__ = [
    "AssessmentEngine", "AssessmentEvidence", "AssessmentKind", "Intervention",
    "CodeFinding", "CodeLabEngine", "CodeReview", "CodeTask", "FindingSeverity",
    "CodingPhase", "CoCodingAction", "CoCodingContext", "HandoffStage", "InteractionPattern",
    "choose_action", "next_handoff",
    "CurriculumGraph", "CurriculumNode", "LearningRecommendation", "rank_recommendations",
    "SchoolEngine", "SchoolPlan", "LearningControl", "LearningControlDecision", "LearningState",
    "LearnerMemory", "MemoryKind", "MemoryMatch", "MemoryStore",
    "PromptRefinement", "RefinementNeed", "refine_prompt",
    "SkillState", "StudentProfile",
]
