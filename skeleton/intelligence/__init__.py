"""
Skeleton Intelligence Package

Exports:
- IntelligenceOrchestrator: Task coordination
- AdaptiveLearner: Meta-learning
- MetaGrid: Learning hyperparameters
- default_meta_grid: Factory for default grid
"""

from skeleton.intelligence.orchestrator import (
    AdaptiveLearner,
    IntelligenceOrchestrator,
    MetaGrid,
    ReasoningResult,
    ReasoningTask,
    default_meta_grid,
)

__all__ = [
    "IntelligenceOrchestrator",
    "AdaptiveLearner",
    "MetaGrid",
    "default_meta_grid",
    "ReasoningTask",
    "ReasoningResult",
]
