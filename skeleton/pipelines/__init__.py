"""
Skeleton Pipelines Package

Exports content generators, the end-to-end GameForge orchestrator, and the
structured game-creation planning contracts used before materialisation.
"""

from skeleton.pipelines.generation import (
    AnimationPipeline,
    AnimationSpec,
    GameLogicPipeline,
    GameLogicSpec,
    NPCPipeline,
    NPCSpec,
)
from skeleton.pipelines.game_creation import (
    CreationAssessment,
    GameCreationPlan,
    GameCreationPlanner,
    GameCreationResult,
    GameSystem,
    PlaytestProbe,
)
from skeleton.pipelines.gameforge import GameForge, GameSpec

__all__ = [
    "NPCPipeline",
    "NPCSpec",
    "GameLogicPipeline",
    "GameLogicSpec",
    "AnimationPipeline",
    "AnimationSpec",
    "GameSystem",
    "PlaytestProbe",
    "CreationAssessment",
    "GameCreationPlan",
    "GameCreationResult",
    "GameCreationPlanner",
    "GameForge",
    "GameSpec",
]
