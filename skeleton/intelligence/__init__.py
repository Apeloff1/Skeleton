"""
Skeleton Intelligence Package

Exports:
- IntelligenceOrchestrator: Task coordination
- AdaptiveLearner: Meta-learning
- MetaGrid: Learning hyperparameters
- default_meta_grid: Factory for default grid
- ImproveLoop / PrefixImprover: bounded self-improvement (F-10)
"""

from skeleton.intelligence.orchestrator import (
    AdaptiveLearner,
    IntelligenceOrchestrator,
    MetaGrid,
    ReasoningResult,
    ReasoningTask,
    default_meta_grid,
)
from skeleton.intelligence.improve_loop import ImproveLoop, ImproveResult, Iteration
from skeleton.intelligence.prefix_improve import (
    AnswerQualitySignal,
    PrefixImproveResult,
    PrefixImprover,
    PrefixVariant,
    adapt_plane_learner,
    improve_prefix,
    seed_from_renderer,
    seed_from_segments,
)

__all__ = [
    "IntelligenceOrchestrator",
    "AdaptiveLearner",
    "MetaGrid",
    "default_meta_grid",
    "ReasoningTask",
    "ReasoningResult",
    "ImproveLoop",
    "ImproveResult",
    "Iteration",
    "PrefixImprover",
    "PrefixImproveResult",
    "PrefixVariant",
    "AnswerQualitySignal",
    "adapt_plane_learner",
    "improve_prefix",
    "seed_from_segments",
    "seed_from_renderer",
]
