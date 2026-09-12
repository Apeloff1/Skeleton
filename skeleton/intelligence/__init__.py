"""Skeleton Intelligence Package.

Exports orchestration, learning, pedagogy, world governance, narrative,
quest planning and live collaboration primitives for the Jeeves school AI.
"""
from skeleton.intelligence.orchestrator import AdaptiveLearner, IntelligenceOrchestrator, MetaGrid, ReasoningResult, ReasoningTask, default_meta_grid
from skeleton.intelligence.improve_loop import ImproveLoop, ImproveResult, Iteration
from skeleton.intelligence.prompt_improve import PrefixVariant, PromptImproveDriver, PromptImproveResult, answer_quality_score, improve_prefix_prompt, mutate_prefix
from skeleton.intelligence.jeeves_policy import InteractionMode, LearningPolicy, LearningStage, choose_difficulty, interaction_mode, stage_for_hours
from skeleton.intelligence.game_context import FactionContext, NoveltyDecision, reputation_level, novelty_gate, GAMEFORGE_DOCTRINE
from skeleton.intelligence.jeeves_pedagogy import *
from skeleton.intelligence.collaboration import CollaborationContext, CollaborationRole, collaboration_prompt, suggestion_window
from skeleton.intelligence.narrative import DialogueChoice, DialogueGraph, DialogueNode, DialogueState, NpcRelationship
from skeleton.intelligence.quests import QuestObjective, QuestProgress, QuestTemplate, rank_quest_candidates

__all__ = [
    "IntelligenceOrchestrator", "AdaptiveLearner", "MetaGrid", "default_meta_grid", "ReasoningTask", "ReasoningResult",
    "ImproveLoop", "ImproveResult", "Iteration", "PrefixVariant", "PromptImproveDriver", "PromptImproveResult",
    "answer_quality_score", "improve_prefix_prompt", "mutate_prefix", "InteractionMode", "LearningPolicy", "LearningStage",
    "choose_difficulty", "interaction_mode", "stage_for_hours", "FactionContext", "NoveltyDecision", "reputation_level",
    "novelty_gate", "GAMEFORGE_DOCTRINE", "CollaborationContext", "CollaborationRole", "collaboration_prompt",
    "suggestion_window", "DialogueChoice", "DialogueGraph", "DialogueNode", "DialogueState", "NpcRelationship",
    "QuestObjective", "QuestProgress", "QuestTemplate", "rank_quest_candidates",
]
