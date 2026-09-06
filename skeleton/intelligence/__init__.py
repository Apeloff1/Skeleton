"""
Skeleton Intelligence Package

Exports:
- IntelligenceOrchestrator: Task coordination
- AdaptiveLearner: Meta-learning
- MetaGrid: Learning hyperparameters
- default_meta_grid: Factory for default grid
- ImproveLoop / PromptImproveDriver: bounded prompt self-improvement (F-10)
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
from skeleton.intelligence.prompt_improve import (
    PrefixVariant,
    PromptImproveDriver,
    PromptImproveResult,
    answer_quality_score,
    improve_prefix_prompt,
    mutate_prefix,
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
    "PrefixVariant",
    "PromptImproveDriver",
    "PromptImproveResult",
    "answer_quality_score",
    "improve_prefix_prompt",
    "mutate_prefix",
]
