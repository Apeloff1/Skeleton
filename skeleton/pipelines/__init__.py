"""
Skeleton Pipelines Package

Exports:
- NPCPipeline / GameLogicPipeline / AnimationPipeline: Content generators
- GameForge: End-to-end game generation orchestrator
- GameSpec: Packaged output artifact
"""

from skeleton.pipelines.generation import (
    AnimationPipeline,
    AnimationSpec,
    GameLogicPipeline,
    GameLogicSpec,
    NPCPipeline,
    NPCSpec,
)
from skeleton.pipelines.gameforge import GameForge, GameSpec

__all__ = [
    "NPCPipeline",
    "NPCSpec",
    "GameLogicPipeline",
    "GameLogicSpec",
    "AnimationPipeline",
    "AnimationSpec",
    "GameForge",
    "GameSpec",
]
