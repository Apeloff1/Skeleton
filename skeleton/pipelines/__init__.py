"""Text-to-X pipelines plus generic runner, resilience wrappers, and helpers."""

from skeleton.pipelines.animation import AnimationPipeline, AnimationSpec
from skeleton.pipelines.cache import PipelineCache
from skeleton.pipelines.core import (
    PipelineContext,
    PipelineRunner,
    Stage,
    StageResult,
)
from skeleton.pipelines.game_logic import GameLogicPipeline, GameLogicSpec
from skeleton.pipelines.hooks import Hook, HookError, HookPoint, HookRegistry
from skeleton.pipelines.npc import NpcPipeline, NpcSpec
from skeleton.pipelines.parallel import ParallelRunner
from skeleton.pipelines.registry import PipelineRegistry, RegistryError
from skeleton.pipelines.resilience import ResilientRunner
from skeleton.pipelines.retry import RetryError, RetryStage
from skeleton.pipelines.seeds import SeedRegistry, StageSeed
from skeleton.pipelines.validation import (
    StageValidatorRegistry,
    ValidationIssue,
    ValidationIssueLevel,
    ValidationReport,
    Validator,
)

__all__ = [
    "AnimationPipeline",
    "AnimationSpec",
    "PipelineCache",
    "PipelineContext",
    "PipelineRunner",
    "Stage",
    "StageResult",
    "GameLogicPipeline",
    "GameLogicSpec",
    "Hook",
    "HookError",
    "HookPoint",
    "HookRegistry",
    "NpcPipeline",
    "NpcSpec",
    "ParallelRunner",
    "PipelineRegistry",
    "RegistryError",
    "ResilientRunner",
    "RetryError",
    "RetryStage",
    "SeedRegistry",
    "StageSeed",
    "StageValidatorRegistry",
    "ValidationIssue",
    "ValidationIssueLevel",
    "ValidationReport",
    "Validator",
]
