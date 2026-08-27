"""Text-to-X generation pipelines plus the generic stage runner.

Each domain pipeline (npc, game_logic, animation) is an application service;
`core` provides the generic DAG runner any new pipeline can build on.
"""

from skeleton.pipelines.npc import NpcPipeline, NpcSpec
from skeleton.pipelines.game_logic import GameLogicPipeline, GameLogicSpec
from skeleton.pipelines.animation import AnimationPipeline, AnimationSpec
from skeleton.pipelines.core import (
    PipelineContext,
    PipelineRunner,
    Stage,
    StageResult,
)

__all__ = [
    "NpcPipeline",
    "NpcSpec",
    "GameLogicPipeline",
    "GameLogicSpec",
    "AnimationPipeline",
    "AnimationSpec",
    "PipelineContext",
    "PipelineRunner",
    "Stage",
    "StageResult",
]
