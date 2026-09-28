"""Static build audits.

This package is additive. Hidden network-command classification lives in
``network_audit``. Content-addressed incremental graph compilation (#940)
is a sibling concern and is not defined here.
"""

from skeleton.build.asset_pipeline import (
    ASSET_PIPELINE_ALGORITHM,
    ASSET_PIPELINE_SCHEMA,
    AssetDescriptor,
    AssetPipeline,
    AssetPipelineError,
    AssetRebuildPlan,
    AssetSpec,
    build_asset_pipeline,
    plan_asset_rebuild,
)

from skeleton.build.cache_contract import (
    CACHE_ALGORITHM,
    CACHE_KEY_PREFIX,
    CACHE_KINDS,
    CACHE_SCHEMA,
    CacheContractError,
    CacheEntry,
    CacheKey,
    EvictionPlan,
    EvictionPolicy,
    build_cache_key,
    plan_eviction,
)

from skeleton.build.incremental_graph import (
    FINGERPRINT_ALGORITHM,
    GRAPH_SCHEMA,
    MAX_EDGES,
    MAX_NODES,
    MAX_TRAVERSAL_VISITS,
    CriticalPath,
    GraphNode,
    IncrementalBuildGraph,
    IncrementalGraphError,
    NodeSpec,
    build_incremental_graph,
)

from skeleton.build.network_audit import (
    CLASSIFICATION_NETWORK_REQUIRED,
    CLASSIFICATION_NETWORK_UNKNOWN,
    CLASSIFICATION_OFFLINE,
    CONFLICT_DOMAIN,
    KIND,
    SCHEMA_VERSION,
    TASK_ID,
    CommandFinding,
    NetworkAuditReport,
    audit_repository,
    classify_action_ref,
    classify_command,
    network_audit_snapshot,
)

__all__ = [
    "plan_asset_rebuild",
    "build_asset_pipeline",
    "AssetSpec",
    "AssetRebuildPlan",
    "AssetPipelineError",
    "AssetPipeline",
    "AssetDescriptor",
    "ASSET_PIPELINE_SCHEMA",
    "ASSET_PIPELINE_ALGORITHM",
    "plan_eviction",
    "build_cache_key",
    "EvictionPolicy",
    "EvictionPlan",
    "CacheKey",
    "CacheEntry",
    "CacheContractError",
    "CACHE_SCHEMA",
    "CACHE_KINDS",
    "CACHE_KEY_PREFIX",
    "CACHE_ALGORITHM",
    "build_incremental_graph",
    "NodeSpec",
    "IncrementalGraphError",
    "IncrementalBuildGraph",
    "GraphNode",
    "CriticalPath",
    "MAX_TRAVERSAL_VISITS",
    "MAX_NODES",
    "MAX_EDGES",
    "GRAPH_SCHEMA",
    "FINGERPRINT_ALGORITHM",
    "CLASSIFICATION_NETWORK_REQUIRED",
    "CLASSIFICATION_NETWORK_UNKNOWN",
    "CLASSIFICATION_OFFLINE",
    "CONFLICT_DOMAIN",
    "KIND",
    "SCHEMA_VERSION",
    "TASK_ID",
    "CommandFinding",
    "NetworkAuditReport",
    "audit_repository",
    "classify_action_ref",
    "classify_command",
    "network_audit_snapshot",
]
