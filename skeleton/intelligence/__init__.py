"""Intelligence package — quad-system cognitive substrate (split from the v16 monolith)."""

from ._tensor import Tensor
from .temporal import TemporalEvent, TemporalReasoner
from .causal import CausalVariable, CausalGraph, CausalInference
from .counterfactual import CounterfactualEngine, CounterfactualError, StructuralModel
from .metalearning import TaskEmbedding, MetaLearner
from .neurosymbolic import SymbolicRule, NeuralSymbolicEngine
from .economic import ModelOption, BudgetConstraint, EconomicOptimiser
from .orchestrator import IntelligenceOrchestrator

__all__ = [
    'Tensor',
    'TemporalEvent',
    'TemporalReasoner',
    'CausalVariable',
    'CausalGraph',
    'CausalInference',
    'CounterfactualEngine',
    'CounterfactualError',
    'StructuralModel',
    'TaskEmbedding',
    'MetaLearner',
    'SymbolicRule',
    'NeuralSymbolicEngine',
    'ModelOption',
    'BudgetConstraint',
    'EconomicOptimiser',
    'IntelligenceOrchestrator'
]
