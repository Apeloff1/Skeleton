"""Skeleton Intelligence Package

Exports core orchestration, bounded self-improvement, adaptive Jeeves learning,
game context, and portable Jeeves pedagogy primitives.
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
from skeleton.intelligence.jeeves_pedagogy import (
    AssessmentKind,
    ScaffoldLevel,
    LearningSession,
    RetrievalReview,
    RETRIEVAL_SCHEDULE,
    SOCRATIC_QUESTION_TYPES,
    WORKED_EXAMPLE_FADING,
    assessment_strategy,
    build_session,
    choose_session_structure,
    interleave_topics,
    next_scaffold,
    retrieval_schedule,
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
    "AssessmentKind",
    "ScaffoldLevel",
    "LearningSession",
    "RetrievalReview",
    "RETRIEVAL_SCHEDULE",
    "SOCRATIC_QUESTION_TYPES",
    "WORKED_EXAMPLE_FADING",
    "assessment_strategy",
    "build_session",
    "choose_session_structure",
    "interleave_topics",
    "next_scaffold",
    "retrieval_schedule",
]
