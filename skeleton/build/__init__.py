"""Deterministic content-addressed incremental build graph.

Conflict domain: ``build.incremental_graph``. This package is a planning
primitive only: it never executes build commands, opens a network, or
bootstraps a toolchain. Trusted repository-intelligence snapshots may be
consumed as source nodes; the scanner itself is out of scope.
"""

from skeleton.build.incremental_graph import (
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

__all__ = [
    "GRAPH_SCHEMA",
    "MAX_EDGES",
    "MAX_NODES",
    "MAX_TRAVERSAL_VISITS",
    "CriticalPath",
    "GraphNode",
    "IncrementalBuildGraph",
    "IncrementalGraphError",
    "NodeSpec",
    "build_incremental_graph",
]
