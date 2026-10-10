"""Repository-intelligence primitives."""

from .batch_plan import (
    BATCH_COUNT,
    LANES,
    PLAN_PATH,
    BatchPlan,
    BatchPlanError,
    BatchSpec,
    load_plan,
    snapshot_b001,
)
from .git_index import GitIndex, GitIndexError, GitIndexSnapshot, TrackedFile

__all__ = [
    "BATCH_COUNT",
    "LANES",
    "PLAN_PATH",
    "BatchPlan",
    "BatchPlanError",
    "BatchSpec",
    "GitIndex",
    "GitIndexError",
    "GitIndexSnapshot",
    "TrackedFile",
    "load_plan",
    "snapshot_b001",
]

from .repository_graph import DependencyEdge, FileNode, RepositoryGraph, RepositoryGraphError
from .change_planner import ChangePlan, plan_change
from .source_extraction import MAX_SOURCE_BYTES, SourceFile, build_repository_graph
