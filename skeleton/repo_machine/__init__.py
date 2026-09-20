"""Machine-native repository organization and topology plane.

Deterministic standard-library tooling for autonomous repository understanding,
organization, growth planning, impact analysis and bounded stewardship.
Repository files are inspected as data and are never imported or executed by
this package.
"""

from .architecture_layers import (
    ArchitectureLayer,
    ArchitectureLayers,
    dependency_direction_violations,
    derive_architecture_layers,
)
from .budgets import ZoneBudget, derive_zone_budgets
from .builder import RepositoryModelBuilder, build_repository_model
from .catalog import CapabilityRecord, RepositoryCatalog, build_catalog
from .checkpoint import ObjectiveOutcome, StewardCheckpoint
from .context import context_for_intent
from .context_budget import ContextAllocation, allocate_context
from .contracts import SubsystemContract, derive_contracts
from .coordinator import CoordinatorSnapshot, build_coordinator_snapshot
from .debt import DebtItem, debt_by_zone, debt_register
from .docs_map import DocumentationCoverage, documentation_coverage
from .evolution import EvolutionReport, evaluate_evolution
from .governance import GovernanceViolation, validate_governance
from .growth import GrowthRecommendation, growth_recommendations
from .health import HealthReport, repository_health
from .hotspots import Hotspot, structural_hotspots
from .impact import ImpactReport, analyze_impact
from .intent import ChangeIntent, IntentAssessment, assess_change_intent
from .leases import LeaseRegistry, WorkLease
from .manifest import ManifestDelta, compare_manifest_states, save_manifest
from .metrics import StructureMetrics, structural_metrics
from .migration import MigrationPlan, build_migration_plan
from .model import (
    FileRecord,
    Finding,
    RepositoryModel,
    SubsystemRecord,
    TopologyEdge,
    ZoneRule,
)
from .model_diff import RepositoryModelDelta, compare_models
from .naming import NamingFinding, analyze_naming
from .navigation import NavigationIndex
from .ownership import OwnershipReport, analyze_ownership
from .package_graph import PackageUnit, discover_package_units
from .parallel_plan import WorkWave, build_parallel_waves
from .planner import WorkCandidate, derive_work_candidates
from .policy import PolicyDecision, evaluate_change_policy
from .protocol import MachineRequest, MachineResponse, handle_request
from .query import RepositoryQuery
from .refactor import RefactorPlan, plan_refactors
from .relations import Relation, build_relations, reachable_files
from .reorganize import ReorganizationProposal, propose_reorganization
from .retrieval import RepositoryRetrievalIndex, SearchHit
from .scheduler import ScheduledObjective, schedule_objectives
from .selfcheck import SelfCheckFinding, run_selfcheck, selfcheck_ok
from .session import MachineSession, build_machine_session
from .shards import ContextShard, build_context_shards, shard_index
from .steward import StewardObjective, StewardPlan, select_steward_plan
from .test_affinity import TestAffinity, build_test_affinity
from .validation_plan import ValidationPlan, build_validation_plan
from .work_queue import MachineWorkQueue, QueueItem
from .workgraph import WorkGraph, WorkNode, build_work_graph
from .workspace import generate_workspace

__all__ = [
    "ArchitectureLayer",
    "ArchitectureLayers",
    "CapabilityRecord",
    "ChangeIntent",
    "ContextAllocation",
    "ContextShard",
    "CoordinatorSnapshot",
    "DebtItem",
    "DocumentationCoverage",
    "EvolutionReport",
    "FileRecord",
    "Finding",
    "GovernanceViolation",
    "GrowthRecommendation",
    "HealthReport",
    "Hotspot",
    "ImpactReport",
    "IntentAssessment",
    "LeaseRegistry",
    "MachineRequest",
    "MachineResponse",
    "MachineSession",
    "MachineWorkQueue",
    "ManifestDelta",
    "MigrationPlan",
    "NamingFinding",
    "NavigationIndex",
    "ObjectiveOutcome",
    "OwnershipReport",
    "PackageUnit",
    "PolicyDecision",
    "QueueItem",
    "RefactorPlan",
    "Relation",
    "ReorganizationProposal",
    "RepositoryCatalog",
    "RepositoryModel",
    "RepositoryModelBuilder",
    "RepositoryModelDelta",
    "RepositoryQuery",
    "RepositoryRetrievalIndex",
    "ScheduledObjective",
    "SearchHit",
    "SelfCheckFinding",
    "StewardCheckpoint",
    "StewardObjective",
    "StewardPlan",
    "StructureMetrics",
    "SubsystemContract",
    "SubsystemRecord",
    "TestAffinity",
    "TopologyEdge",
    "ValidationPlan",
    "WorkCandidate",
    "WorkGraph",
    "WorkLease",
    "WorkNode",
    "WorkWave",
    "ZoneBudget",
    "ZoneRule",
    "allocate_context",
    "analyze_impact",
    "analyze_naming",
    "analyze_ownership",
    "assess_change_intent",
    "build_catalog",
    "build_context_shards",
    "build_coordinator_snapshot",
    "build_machine_session",
    "build_migration_plan",
    "build_parallel_waves",
    "build_relations",
    "build_repository_model",
    "build_test_affinity",
    "build_validation_plan",
    "build_work_graph",
    "compare_manifest_states",
    "compare_models",
    "context_for_intent",
    "debt_by_zone",
    "debt_register",
    "dependency_direction_violations",
    "derive_architecture_layers",
    "derive_contracts",
    "derive_work_candidates",
    "derive_zone_budgets",
    "discover_package_units",
    "documentation_coverage",
    "evaluate_change_policy",
    "evaluate_evolution",
    "generate_workspace",
    "growth_recommendations",
    "handle_request",
    "plan_refactors",
    "propose_reorganization",
    "reachable_files",
    "repository_health",
    "run_selfcheck",
    "save_manifest",
    "schedule_objectives",
    "select_steward_plan",
    "selfcheck_ok",
    "shard_index",
    "structural_hotspots",
    "structural_metrics",
    "validate_governance",
]
