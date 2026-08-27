"""Text-to-X generation pipelines plus the generic stage runner."""

from skeleton.pipelines.npc import NpcPipeline, NpcSpec
from skeleton.pipelines.game_logic import GameLogicPipeline, GameLogicSpec
from skeleton.pipelines.animation import AnimationPipeline, AnimationSpec
from skeleton.pipelines.core import (
    PipelineContext,
    PipelineRunner,
    Stage,
    StageResult,
)
from skeleton.pipelines.validation import (
    StageValidatorRegistry,
    ValidationIssue,
    ValidationIssueLevel,
    ValidationReport,
    Validator,
)
from skeleton.pipelines.registry import PipelineRegistry, RegistryError
from skeleton.pipelines.hooks import Hook, HookError, HookPoint, HookRegistry

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
    "StageValidatorRegistry",
    "ValidationIssue",
    "ValidationIssueLevel",
    "ValidationReport",
    "Validator",
    "PipelineRegistry",
    "RegistryError",
    "Hook",
    "HookError",
    "HookPoint",
    "HookRegistry",
]
