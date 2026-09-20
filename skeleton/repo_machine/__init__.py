"""Machine-native repository organization and topology plane.

This package is intentionally deterministic and standard-library only.  It
models repository structure as bounded data for automation, without importing
or executing discovered repository code.
"""

from .builder import RepositoryModelBuilder, build_repository_model
from .model import (
    FileRecord,
    Finding,
    RepositoryModel,
    SubsystemRecord,
    TopologyEdge,
    ZoneRule,
)
from .planner import WorkCandidate, derive_work_candidates

__all__ = [
    "FileRecord",
    "Finding",
    "RepositoryModel",
    "RepositoryModelBuilder",
    "SubsystemRecord",
    "TopologyEdge",
    "WorkCandidate",
    "ZoneRule",
    "build_repository_model",
    "derive_work_candidates",
]
