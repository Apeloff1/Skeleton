"""
Skeleton Persistence Package

Exports:
- SnapshotStore: File-based snapshot registry
- snapshot_genesis_state / restore_genesis_state: whole-system capture
- Plane serializers for VectorStore, MAGStore, KnowledgeGraph, matrices
"""

from skeleton.persistence.snapshots import (
    SnapshotStore,
    restore_genesis_state,
    restore_graph,
    restore_mag,
    restore_matrices,
    restore_vector_store,
    serialize_graph,
    serialize_mag,
    serialize_matrices,
    serialize_vector_store,
    snapshot_genesis_state,
)

__all__ = [
    "SnapshotStore",
    "snapshot_genesis_state",
    "restore_genesis_state",
    "serialize_vector_store",
    "restore_vector_store",
    "serialize_mag",
    "restore_mag",
    "serialize_graph",
    "restore_graph",
    "serialize_matrices",
    "restore_matrices",
]
