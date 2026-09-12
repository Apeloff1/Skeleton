"""School primitives for the Tutolage + Jeeves learning core."""

from skeleton.school.assessment import AssessmentEngine, AssessmentEvidence, AssessmentKind, Intervention
from skeleton.school.code_intelligence import CodeIntelligenceEngine, CodeIntelligenceReport, CodeSignal, CodeSignalKind, CodeTask as IntelligenceTask, CodeTaskKind
from skeleton.school.code_lab import CodeFinding, CodeLabEngine, CodeReview, CodeTask, FindingSeverity
from skeleton.school.cocoding import CodingPhase, CoCodingAction, CoCodingContext, HandoffStage, InteractionPattern, choose_action, next_handoff
from skeleton.school.curriculum import CurriculumGraph, CurriculumNode, LearningRecommendation, rank_recommendations
from skeleton.school.debugging import DebugAction, DebugExperiment, DebugFocus, DebugHypothesis, DebugPlan, DebuggingPolicy
from skeleton.school.energy import EnergyBudget, EnergyDecision, EnergyStrategy, choose_energy_strategy
from skeleton.school.engine import SchoolEngine, SchoolPlan
from skeleton.school.cs_pathways import CSFamily, CSPathway, PATHWAYS, next_pathway, pathways_for
from skeleton.school.learning_control import LearningControl, LearningControlDecision, LearningState
from skeleton.school.lesson_content import LessonContent, LessonExercise, LessonTopic, generate_lesson_content
from skeleton.school.memory import LearnerMemory, MemoryKind, MemoryMatch, MemoryStore
from skeleton.school.jeeves import JeevesControlPlane, JeevesDecision, JeevesSessionPlan
from skeleton.school.progression import AchievementEvidence, AchievementRequirement, AchievementResult, ProgressionSnapshot, achievement_learning_signal, evaluate_achievement, evaluate_progression
from skeleton.school.prompting import PromptRefinement, RefinementNeed, refine_prompt
from skeleton.school.reflection import ReflectionEntry, ReflectionImportance, ReflectionJournal, ReflectionKind, ReflectionPrompt, reflection_prompts, summarize_reflection
from skeleton.school.student import SkillState, StudentProfile

__all__ = [
    "AssessmentEngine", "AssessmentEvidence", "AssessmentKind", "Intervention",
    "CodeIntelligenceEngine", "CodeIntelligenceReport", "CodeSignal", "CodeSignalKind", "IntelligenceTask", "CodeTaskKind",
    "CodeFinding", "CodeLabEngine", "CodeReview", "CodeTask", "FindingSeverity",
    "CodingPhase", "CoCodingAction", "CoCodingContext", "HandoffStage", "InteractionPattern",
    "choose_action", "next_handoff",
    "CurriculumGraph", "CurriculumNode", "LearningRecommendation", "rank_recommendations",
    "DebugAction", "DebugExperiment", "DebugFocus", "DebugHypothesis", "DebugPlan", "DebuggingPolicy",
    "EnergyBudget", "EnergyDecision", "EnergyStrategy", "choose_energy_strategy",
    "SchoolEngine", "SchoolPlan", "CSFamily", "CSPathway", "PATHWAYS", "next_pathway", "pathways_for",
    "LearningControl", "LearningControlDecision", "LearningState",
    "LessonContent", "LessonExercise", "LessonTopic", "generate_lesson_content",
    "LearnerMemory", "MemoryKind", "MemoryMatch", "MemoryStore",
    "JeevesControlPlane", "JeevesDecision", "JeevesSessionPlan",
    "AchievementEvidence", "AchievementRequirement", "AchievementResult", "ProgressionSnapshot", "achievement_learning_signal", "evaluate_achievement", "evaluate_progression",
    "PromptRefinement", "RefinementNeed", "refine_prompt",
    "ReflectionEntry", "ReflectionImportance", "ReflectionJournal", "ReflectionKind", "ReflectionPrompt", "reflection_prompts", "summarize_reflection",
    "SkillState", "StudentProfile",
]
