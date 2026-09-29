"""School primitives for the Tutolage + Jeeves learning core."""

from skeleton.learning.school.ai_pipeline import PipelineKind, PipelinePlan, PipelineRequest, PipelineStage, PipelineStep, pipeline_capabilities, plan_pipeline
from skeleton.learning.school.assessment import AssessmentEngine, AssessmentEvidence, AssessmentKind, Intervention
from skeleton.learning.school.code_intelligence import CodeIntelligenceEngine, CodeIntelligenceReport, CodeSignal, CodeSignalKind, CodeTask as IntelligenceTask, CodeTaskKind
from skeleton.learning.school.code_lab import CodeFinding, CodeLabEngine, CodeReview, CodeTask, FindingSeverity
from skeleton.learning.school.cocoding import CodingPhase, CoCodingAction, CoCodingContext, HandoffStage, InteractionPattern, choose_action, next_handoff
from skeleton.learning.school.counterfactual import CandidateAction, CounterfactualResult, PolicyCandidate, compete, default_candidates
from skeleton.learning.school.curriculum import CurriculumGraph, CurriculumNode, LearningRecommendation, rank_recommendations
from skeleton.learning.school.debugging import DebugAction, DebugExperiment, DebugFocus, DebugHypothesis, DebugPlan, DebuggingPolicy
from skeleton.learning.school.decision_ledger import DecisionDisposition, DecisionLedger, DecisionRecord, EvidenceKind, EvidenceRef, LedgerCheckpoint, evidence_bundle
from skeleton.learning.school.decision_policy import ArbitrationAction, ArbitrationResult, EvidenceSignal, arbitrate
from skeleton.learning.school.energy import EnergyBudget, EnergyDecision, EnergyStrategy, choose_energy_strategy
from skeleton.learning.school.engine import SchoolEngine, SchoolPlan
from skeleton.learning.school.cs_pathways import CSFamily, CSPathway, PATHWAYS, next_pathway, pathways_for
from skeleton.learning.school.epistemics import BeliefState, EpistemicEngine, EpistemicEvidence, EpistemicUpdate, EvidencePolarity, MisconceptionStage, contradiction_matrix
from skeleton.learning.school.knowledge import KnowledgeAssertion, KnowledgeCandidate, KnowledgeEdge, KnowledgeGraph, KnowledgeNode, KnowledgeState, RelationKind, infer_ready_frontier, rank_knowledge
from skeleton.learning.school.learning_control import LearningControl, LearningControlDecision, LearningState
from skeleton.learning.school.lesson_content import LessonContent, LessonExercise, LessonTopic, generate_lesson_content
from skeleton.learning.school.memory import LearnerMemory, MemoryKind, MemoryMatch, MemoryStore
from skeleton.learning.school.jeeves import JeevesControlPlane, JeevesDecision, JeevesSessionPlan
from skeleton.learning.school.outcomes import OutcomeKind, OutcomeResult, SessionOutcome, apply_outcome
from skeleton.learning.school.policy_calibration import PolicyCalibrator, PolicyStats
from skeleton.learning.school.progression import AchievementEvidence, AchievementRequirement, AchievementResult, ProgressionSnapshot, achievement_learning_signal, evaluate_achievement, evaluate_progression
from skeleton.learning.school.prompting import PromptRefinement, RefinementNeed, refine_prompt
from skeleton.learning.school.reflection import ReflectionEntry, ReflectionImportance, ReflectionJournal, ReflectionKind, ReflectionPrompt, reflection_prompts, summarize_reflection
from skeleton.learning.school.replay import JeevesReplay, ReplayMismatch, ReplayReport, ReplaySnapshot, replay_digest
from skeleton.learning.school.runtime_replay import RuntimeAudit, RuntimeReplaySnapshot, audit_runtime, replay_digest as runtime_replay_digest
from skeleton.learning.school.runtime_audit_api import capture_runtime, complete_runtime
from skeleton.learning.school.runtime_attestation import RuntimeAttestation, verify_attestation
from skeleton.learning.school.runtime_capsule import RuntimeIntegrityCapsule
from skeleton.learning.school.session_audit import SessionAudit, audit_session, policy_chain
from skeleton.learning.school.session_runtime import EvidenceGate, JeevesSessionRuntime, RuntimePlan, SessionEvent, SessionPhase, SessionTransition, TransitionKind
from skeleton.learning.school.session import JeevesSessionEngine, SessionDecision
from skeleton.learning.school.student import SkillState, StudentProfile

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
    "JeevesReplay", "ReplayMismatch", "ReplayReport", "ReplaySnapshot", "replay_digest",
    "RuntimeAudit", "RuntimeReplaySnapshot", "audit_runtime", "runtime_replay_digest", "capture_runtime", "complete_runtime", "RuntimeAttestation", "verify_attestation", "RuntimeIntegrityCapsule",
    "SessionAudit", "audit_session", "policy_chain",
    "EvidenceGate", "JeevesSessionRuntime", "RuntimePlan", "SessionEvent", "SessionPhase", "SessionTransition", "TransitionKind",
    "JeevesSessionEngine", "SessionDecision", "SkillState", "StudentProfile",
]
