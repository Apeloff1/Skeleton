"""
Skeleton — Round-5 architecture addendum

Persistence round: snapshot/restore for RAG, MAG, KAG, Jeeves matrices;
harness restore-on-boot / snapshot-on-shutdown; CLI + dev CLI commands.
"""

from __future__ import annotations

from typing import Any, Dict


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.persistence.snapshots": {
        "layer": "persistence",
        "purpose": "SnapshotStore + plane serializers (RAG/MAG/KAG/matrices) + whole-genesis capture",
        "exports": ["SnapshotStore", "snapshot_genesis_state", "restore_genesis_state"],
    },
    "skeleton.developer.persistence_commands": {
        "layer": "developer",
        "purpose": "Dev CLI snapshot / restore / snapshots commands",
        "exports": ["SnapshotCommand", "RestoreCommand", "SnapshotsCommand"],
    },
}

COMMANDS_ADDED = {
    "deploy.py": ["snapshot", "restore"],
    "skeleton dev": ["snapshot", "restore", "snapshots"],
}

PERSISTED_PLANES = ["rag (vector re-embed on load)", "mag (episodes + tag index)", "kag (triples)", "jeeves matrices (sam/clom/krem)"]


def summary() -> Dict[str, Any]:
    return {
        "round5_modules": len(NEW_MODULES),
        "persisted_planes": PERSISTED_PLANES,
        "commands_added": COMMANDS_ADDED,
        "harness_lifecycle": ["boot(restore=True)", "shutdown(snapshot=True)"],
    }
