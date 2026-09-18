"""Static build audits.

This package is additive. Hidden network-command classification lives in
``network_audit``. Content-addressed incremental graph compilation (#940)
is a sibling concern and is not defined here.
"""

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
