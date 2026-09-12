"""
Skeleton Intelligence Package

Exports:
- IntelligenceOrchestrator: Task coordination
- AdaptiveLearner: Meta-learning
- MetaGrid: Learning hyperparameters
- ImproveLoop / PromptImproveDriver: bounded prompt self-improvement (F-10)
- Jeeves learning policy: stage/difficulty/interaction adaptation
- Game context: faction reputation and novelty governance
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
from skeleton.intelligence.jeeves_policy import (
    InteractionMode,
    LearningPolicy,
    LearningStage,
    choose_difficulty,
    interaction_mode,
    stage_for_hours,
)
from skeleton.intelligence.game_context import (
    FactionContext,
    NoveltyDecision,
    reputation_level,
    novelty_gate,
    GAMEFORGE_DOCTRINE,
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
    "InteractionMode",
    "LearningPolicy",
    "LearningStage",
    "choose_difficulty",
    "interaction_mode",
    "stage_for_hours",
    "FactionContext",
    "NoveltyDecision",
    "reputation_level",
    "novelty_gate",
    "GAMEFORGE_DOCTRINE",
]
