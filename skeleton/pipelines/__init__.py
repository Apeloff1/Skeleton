"""Text-to-X generation pipelines.

Each pipeline is an application service: it orchestrates domain objects, emits
domain events through the bus, and returns immutable results. No HTTP, no
framework imports.
"""

from skeleton.pipelines.npc import NpcPipeline, NpcSpec
from skeleton.pipelines.game_logic import GameLogicPipeline, GameLogicSpec
from skeleton.pipelines.animation import AnimationPipeline, AnimationSpec

__all__ = [
    "NpcPipeline",
    "NpcSpec",
    "GameLogicPipeline",
    "GameLogicSpec",
    "AnimationPipeline",
    "AnimationSpec",
]
