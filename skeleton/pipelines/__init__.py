"""
Skeleton Pipelines Package

Exports:
- NPCPipeline: NPC specification generation
- GameLogicPipeline: Game mechanics design
- AnimationPipeline: Animation specification
- NPCSpec, GameLogicSpec, AnimationSpec: Data types
"""

from skeleton.pipelines.generation import (
    AnimationPipeline,
    AnimationSpec,
    GameLogicPipeline,
    GameLogicSpec,
    NPCPipeline,
    NPCSpec,
)

__all__ = [
    "NPCPipeline",
    "NPCSpec",
    "GameLogicPipeline",
    "GameLogicSpec",
    "AnimationPipeline",
    "AnimationSpec",
]
