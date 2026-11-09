"""School primitives for the Tutolage + Jeeves learning core."""

from skeleton.school.ai_pipeline import PipelineKind, PipelinePlan, PipelineRequest, PipelineStage, PipelineStep, pipeline_capabilities, plan_pipeline
from skeleton.school.assessment import AssessmentEngine, AssessmentEvidence, AssessmentKind, Intervention
from skeleton.school.code_intelligence import CodeIntelligenceEngine, CodeIntelligenceReport, CodeSignal, CodeSignalKind, CodeTask as IntelligenceTask, CodeTaskKind
from skeleton.school.code_lab import CodeFinding, CodeLabEngine, CodeReview, CodeTask, FindingSeverity
from skeleton.school.cocoding import CodingPhase, CoCodingAction, CoCodingContext, HandoffStage, InteractionPattern, choose_action, next_handoff
from skeleton.school.counterfactual import CandidateAction, CounterfactualResult, PolicyCandidate, compete, default_candidates
from skeleton.school.curriculum import CurriculumGraph, CurriculumNode, LearningRecommendation, rank_recommendations
from skeleton.school.debugging import DebugAction, DebugExperiment, DebugFocus, DebugHypothesis, DebugPlan, DebuggingPolicy
from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, DecisionRecord, EvidenceKind, EvidenceRef, LedgerCheckpoint, evidence_bundle
from skeleton.school.decision_policy import ArbitrationAction, ArbitrationResult, EvidenceSignal, arbitrate
from skeleton.school.energy import EnergyBudget, EnergyDecision, EnergyStrategy, choose_energy_strategy
from skeleton.school.engine import SchoolEngine, SchoolPlan
from skeleton.school.cs_pathways import CSFamily, CSPathway, PATHWAYS, next_pathway, pathways_for
from skeleton.school.epistemics import BeliefState, EpistemicEngine, EpistemicEvidence, EpistemicUpdate, EvidencePolarity, MisconceptionStage, contradiction_matrix
from skeleton.school.knowledge import KnowledgeAssertion, KnowledgeCandidate, KnowledgeEdge, KnowledgeGraph, KnowledgeNode, KnowledgeState, RelationKind, infer_ready_frontier, rank_knowledge
from skeleton.school.learning_control import LearningControl, LearningControlDecision, LearningState
from skeleton.school.lesson_content import LessonContent, LessonExercise, LessonTopic, generate_lesson_content
from skeleton.school.memory import LearnerMemory, MemoryKind, MemoryMatch, MemoryStore
from skeleton.school.jeeves import JeevesControlPlane, JeevesDecision, JeevesSessionPlan
from skeleton.school.outcomes import OutcomeKind, OutcomeResult, SessionOutcome, apply_outcome
from skeleton.school.policy_calibration import PolicyCalibrator, PolicyStats
from skeleton.school.progression import AchievementEvidence, AchievementRequirement, AchievementResult, ProgressionSnapshot, achievement_learning_signal, evaluate_achievement, evaluate_progression
from skeleton.school.prompting import PromptRefinement, RefinementNeed, refine_prompt
from skeleton.school.reflection import ReflectionEntry, ReflectionImportance, ReflectionJournal, ReflectionKind, ReflectionPrompt, reflection_prompts, summarize_reflection
from skeleton.school.replay import JeevesReplay, ReplayMismatch, ReplayReport, replay_digest
from skeleton.school.session_runtime import EvidenceGate, JeevesSessionRuntime, RuntimePlan, SessionEvent, SessionPhase, SessionTransition, TransitionKind
from skeleton.school.session import JeevesSessionEngine, SessionDecision
from skeleton.school.student import SkillState, StudentProfile

__all__ = [
    "PipelineKind", "PipelinePlan", "PipelineRequest", "PipelineStage", "PipelineStep", "pipeline_capabilities", "plan_pipeline",
    "AssessmentEngine", "AssessmentEvidence", "AssessmentKind", "Intervention",
    "CodeIntelligenceEngine", "CodeIntelligenceReport", "CodeSignal", "CodeSignalKind", "IntelligenceTask", "CodeTaskKind",
    "CodeFinding", "CodeLabEngine", "CodeReview", "CodeTask", "FindingSeverity",
    "CodingPhase", "CoCodingAction", "CoCodingContext", "HandoffStage", "InteractionPattern", "choose_action", "next_handoff",
    "CandidateAction", "CounterfactualResult", "PolicyCandidate", "compete", "default_candidates",
    "CurriculumGraph", "CurriculumNode", "LearningRecommendation", "rank_recommendations",
    "DebugAction", "DebugExperiment", "DebugFocus", "DebugHypothesis", "DebugPlan", "DebuggingPolicy",
    "DecisionDisposition", "DecisionLedger", "DecisionRecord", "EvidenceKind", "EvidenceRef", "LedgerCheckpoint", "evidence_bundle",
    "ArbitrationAction", "ArbitrationResult", "EvidenceSignal", "arbitrate",
    "EnergyBudget", "EnergyDecision", "EnergyStrategy", "choose_energy_strategy",
    "SchoolEngine", "SchoolPlan", "CSFamily", "CSPathway", "PATHWAYS", "next_pathway", "pathways_for",
    "BeliefState", "EpistemicEngine", "EpistemicEvidence", "EpistemicUpdate", "EvidencePolarity", "MisconceptionStage", "contradiction_matrix",
    "KnowledgeAssertion", "KnowledgeCandidate", "KnowledgeEdge", "KnowledgeGraph", "KnowledgeNode", "KnowledgeState", "RelationKind", "infer_ready_frontier", "rank_knowledge",
    "LearningControl", "LearningControlDecision", "LearningState",
    "LessonContent", "LessonExercise", "LessonTopic", "generate_lesson_content",
    "LearnerMemory", "MemoryKind", "MemoryMatch", "MemoryStore",
    "JeevesControlPlane", "JeevesDecision", "JeevesSessionPlan",
    "OutcomeKind", "OutcomeResult", "SessionOutcome", "apply_outcome",
    "PolicyCalibrator", "PolicyStats",
    "AchievementEvidence", "AchievementRequirement", "AchievementResult", "ProgressionSnapshot", "achievement_learning_signal", "evaluate_achievement", "evaluate_progression",
    "PromptRefinement", "RefinementNeed", "refine_prompt",
    "ReflectionEntry", "ReflectionImportance", "ReflectionJournal", "ReflectionKind", "ReflectionPrompt", "reflection_prompts", "summarize_reflection",
    "JeevesReplay", "ReplayMismatch", "ReplayReport", "replay_digest",
    "EvidenceGate", "JeevesSessionRuntime", "RuntimePlan", "SessionEvent", "SessionPhase", "SessionTransition", "TransitionKind",
    "JeevesSessionEngine", "SessionDecision", "SkillState", "StudentProfile",
]
