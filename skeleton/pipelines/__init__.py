"""
Skeleton Pipelines Package

Exports:
- NPCPipeline / GameLogicPipeline / AnimationPipeline: Content generators
- GameForge: End-to-end game generation orchestrator
- GameSpec: Packaged output artifact
- LorebuffaDialogueRuntime: Stateful domain dialogue execution
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
from skeleton.pipelines.lorebuffa_dialogue import (
    LorebuffaDialogueRuntime,
    LorebuffaDialogueState,
    LorebuffaDialogueTurn,
    completed_marina_dialogue,
)

__all__ = [
    "NPCPipeline",
    "NPCSpec",
    "GameLogicPipeline",
    "GameLogicSpec",
    "AnimationPipeline",
    "AnimationSpec",
    "GameForge",
    "GameSpec",
    "LorebuffaDialogueRuntime",
    "LorebuffaDialogueState",
    "LorebuffaDialogueTurn",
    "completed_marina_dialogue",
]
