"""Intelligence package — quad-system cognitive substrate (split from the v16 monolith)."""

from ._tensor import Tensor
from .temporal import TemporalEvent, TemporalReasoner
from .causal import CausalVariable, CausalGraph, CausalInference
from .metalearning import TaskEmbedding, MetaLearner
from .neurosymbolic import SymbolicRule, NeuralSymbolicEngine
from .economic import ModelOption, BudgetConstraint, EconomicOptimiser
from .orchestrator import IntelligenceOrchestrator
from .dream import DreamReport, DreamEngine

__all__ = [
    'Tensor',
    'TemporalEvent',
    'TemporalReasoner',
    'CausalVariable',
    'CausalGraph',
    'CausalInference',
    'TaskEmbedding',
    'MetaLearner',
    'SymbolicRule',
    'NeuralSymbolicEngine',
    'ModelOption',
    'BudgetConstraint',
    'EconomicOptimiser',
    'IntelligenceOrchestrator',
    'DreamReport',
    'DreamEngine',
]
