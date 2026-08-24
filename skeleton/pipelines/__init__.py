"""Pipelines package — Text-to-X generation services."""

from .dialogue import (
    DialogueEdge,
    DialogueError,
    DialogueNode,
    DialogueTree,
    DialogueWalker,
)
from .composer import (
    Context,
    GateFn,
    PipelineComposer,
    PipelineRun,
    Stage,
    StageFn,
    StageRecord,
    StageStatus,
)

__all__ = [
    "DialogueEdge", "DialogueError", "DialogueNode", "DialogueTree", "DialogueWalker",
    "PipelineComposer", "PipelineRun", "Stage", "StageRecord", "StageStatus",
    "Context", "StageFn", "GateFn",
]
