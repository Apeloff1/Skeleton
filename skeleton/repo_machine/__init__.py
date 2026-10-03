"""Machine-native repository organization and topology plane."""
from __future__ import annotations

from .atlas import AtlasZone, PathPlacement, RepositoryAtlas, build_repository_atlas, placement_for_path
from .budgets import ZoneBudget, derive_zone_budgets
from .builder import RepositoryModelBuilder, build_repository_model
from .catalog import CapabilityRecord, RepositoryCatalog, build_catalog
from .context import context_for_intent
from .contracts import SubsystemContract, derive_contracts
from .execution_plan import ExecutionPlan, ExecutionState, PlanStep, advance_execution, build_execution_plan
from .governance import GovernanceViolation, validate_governance
from .growth import GrowthRecommendation, growth_recommendations
from .health import HealthReport, repository_health
from .hotspots import Hotspot, structural_hotspots
from .impact import ImpactReport, analyze_impact
from .manifest import ManifestDelta, compare_manifest_states, save_manifest
from .metrics import StructureMetrics, structural_metrics
from .model import FileRecord, Finding, RepositoryModel, SubsystemRecord, TopologyEdge, ZoneRule
from .model_diff import RepositoryModelDelta, compare_models
from .navigation import NavigationIndex
from .ownership import OwnershipReport, analyze_ownership
from .planner import WorkCandidate, derive_work_candidates
from .policy import PolicyDecision, evaluate_change_policy
from .query import RepositoryQuery
from .relations import Relation, build_relations, reachable_files
from .reorganize import ReorganizationProposal, propose_reorganization
from .retrieval import RepositoryRetrievalIndex, SearchHit
from .shards import ContextShard, build_context_shards, shard_index
from .steward import StewardObjective, StewardPlan, select_steward_plan
from .workgraph import WorkGraph, WorkNode, build_work_graph
from .workspace import generate_workspace

__all__ = [
    "AtlasZone", "CapabilityRecord", "ContextShard", "ExecutionPlan", "ExecutionState",
    "FileRecord", "Finding", "GovernanceViolation", "GrowthRecommendation", "HealthReport",
    "Hotspot", "ImpactReport", "ManifestDelta", "NavigationIndex", "OwnershipReport",
    "PathPlacement", "PlanStep", "PolicyDecision", "Relation", "ReorganizationProposal",
    "RepositoryAtlas", "RepositoryCatalog", "RepositoryModel", "RepositoryModelBuilder",
    "RepositoryModelDelta", "RepositoryQuery", "RepositoryRetrievalIndex", "SearchHit",
    "StewardObjective", "StewardPlan", "StructureMetrics", "SubsystemContract", "SubsystemRecord",
    "TopologyEdge", "WorkCandidate", "WorkGraph", "WorkNode", "ZoneBudget", "ZoneRule",
    "advance_execution", "analyze_impact", "analyze_ownership", "build_catalog",
    "build_context_shards", "build_execution_plan", "build_relations", "build_repository_atlas",
    "build_repository_model", "build_work_graph", "compare_manifest_states", "compare_models",
    "context_for_intent", "derive_contracts", "derive_work_candidates", "derive_zone_budgets",
    "evaluate_change_policy", "generate_workspace", "growth_recommendations", "placement_for_path",
    "propose_reorganization", "reachable_files", "repository_health", "save_manifest",
    "select_steward_plan", "shard_index", "structural_hotspots", "structural_metrics",
    "validate_governance",
]
