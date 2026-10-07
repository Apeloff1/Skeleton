"""
Skeleton Pipelines Package

Exports:
- NPCPipeline / GameLogicPipeline / AnimationPipeline: Content generators
- GameForge: End-to-end game generation orchestrator
- GameSpec: Packaged output artifact
"""

from skeleton.forge.pipelines.generation import (
    AnimationPipeline,
    AnimationSpec,
    GameLogicPipeline,
    GameLogicSpec,
    NPCPipeline,
    NPCSpec,
)
from skeleton.forge.pipelines.gameforge import GameForge, GameSpec
from skeleton.forge.pipelines.npc import NpcPipeline

__all__ = [
    "NPCPipeline",
    "NpcPipeline",
    "NPCSpec",
    "GameLogicPipeline",
    "GameLogicSpec",
    "AnimationPipeline",
    "AnimationSpec",
    "GameForge",
    "GameSpec",
]
