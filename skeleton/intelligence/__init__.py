"""Intelligence package — quad-system cognitive substrate (split from the v16 monolith)."""

from ._tensor import Tensor
from .temporal import TemporalEvent, TemporalReasoner
from .causal import CausalVariable, CausalGraph, CausalInference
from .counterfactual import CounterfactualEngine, CounterfactualError, StructuralModel
from .metalearning import TaskEmbedding, MetaLearner
from .neurosymbolic import SymbolicRule, NeuralSymbolicEngine
from .economic import ModelOption, BudgetConstraint, EconomicOptimiser
from .orchestrator import IntelligenceOrchestrator
from .adaptive import AdaptiveLearner, Arm, RunRecord, default_meta_grid
from .dream import DreamEngine, DreamReport
from .cascade import CascadeRouter, ModelResponse, RouteDecision, difficulty_estimate
from .uncertainty import Candidate, GateDecision, GateVerdict, UncertaintyGate
from .verification import VerificationLoop, VerificationTrace, VerificationVerdict
from .verifier import CodeVerifier, RubricScore, VerifierReport
from .quality import QualityIssue, QualityReport, QualitySignal
from .plan_verifier import PlanVerifier, PlanVerificationReport
from .pipeline_verifier import PipelineVerifier, PipelineVerificationReport
from .forge_verifier import ForgeVerifier, ForgeVerificationReport, ForgeFileReport
from .improve_loop import ImproveLoop, ImproveResult, Iteration
from .routed_gate import RoutedAnswer, RoutedGate
from .contract import Contract, ContractIssue, RepairResult

__all__ = [
    'Tensor', 'TemporalEvent', 'TemporalReasoner',
    'CausalVariable', 'CausalGraph', 'CausalInference',
    'CounterfactualEngine', 'CounterfactualError', 'StructuralModel',
    'TaskEmbedding', 'MetaLearner', 'SymbolicRule', 'NeuralSymbolicEngine',
    'ModelOption', 'BudgetConstraint', 'EconomicOptimiser',
    'IntelligenceOrchestrator', 'AdaptiveLearner', 'Arm', 'RunRecord',
    'default_meta_grid', 'DreamEngine', 'DreamReport',
    'CascadeRouter', 'ModelResponse', 'RouteDecision', 'difficulty_estimate',
    'Candidate', 'GateDecision', 'GateVerdict', 'UncertaintyGate',
    'VerificationLoop', 'VerificationTrace', 'VerificationVerdict',
    'CodeVerifier', 'RubricScore', 'VerifierReport',
    'QualityIssue', 'QualityReport', 'QualitySignal',
    'PlanVerifier', 'PlanVerificationReport',
    'PipelineVerifier', 'PipelineVerificationReport',
    'ForgeVerifier', 'ForgeVerificationReport', 'ForgeFileReport',
    'ImproveLoop', 'ImproveResult', 'Iteration',
    'RoutedAnswer', 'RoutedGate',
    'Contract', 'ContractIssue', 'RepairResult',
]
