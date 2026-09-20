"""Machine-native repository organization and topology plane.

The package is deterministic and standard-library only. It models repository
structure as bounded data for automation without importing or executing
repository code discovered by the scanner.
"""

from .builder import RepositoryModelBuilder, build_repository_model
from .catalog import CapabilityRecord, RepositoryCatalog, build_catalog
from .context import context_for_intent
from .contracts import SubsystemContract, derive_contracts
from .growth import GrowthRecommendation, growth_recommendations
from .health import HealthReport, repository_health
from .impact import ImpactReport, analyze_impact
from .manifest import ManifestDelta, compare_manifest_states, save_manifest
from .metrics import StructureMetrics, structural_metrics
from .model import (
    FileRecord,
    Finding,
    RepositoryModel,
    SubsystemRecord,
    TopologyEdge,
    ZoneRule,
)
from .navigation import NavigationIndex
from .ownership import OwnershipReport, analyze_ownership
from .planner import WorkCandidate, derive_work_candidates
from .policy import PolicyDecision, evaluate_change_policy
from .shards import ContextShard, build_context_shards, shard_index
from .steward import StewardObjective, StewardPlan, select_steward_plan
from .workgraph import WorkGraph, WorkNode, build_work_graph

__all__ = [
    "CapabilityRecord",
    "ContextShard",
    "FileRecord",
    "Finding",
    "GrowthRecommendation",
    "HealthReport",
    "ImpactReport",
    "ManifestDelta",
    "NavigationIndex",
    "OwnershipReport",
    "PolicyDecision",
    "RepositoryCatalog",
    "RepositoryModel",
    "RepositoryModelBuilder",
    "StewardObjective",
    "StewardPlan",
    "StructureMetrics",
    "SubsystemContract",
    "SubsystemRecord",
    "TopologyEdge",
    "WorkCandidate",
    "WorkGraph",
    "WorkNode",
    "ZoneRule",
    "analyze_impact",
    "analyze_ownership",
    "build_catalog",
    "build_context_shards",
    "build_repository_model",
    "build_work_graph",
    "compare_manifest_states",
    "context_for_intent",
    "derive_contracts",
    "derive_work_candidates",
    "evaluate_change_policy",
    "growth_recommendations",
    "repository_health",
    "save_manifest",
    "select_steward_plan",
    "shard_index",
    "structural_metrics",
]
