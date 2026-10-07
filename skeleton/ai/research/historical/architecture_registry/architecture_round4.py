"""
Skeleton — Round-4 architecture addendum

Registers the modules added in the KAG self-population, swarm bridge,
and Jeeves matrices rounds.
"""

from __future__ import annotations

from typing import Any, Dict


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.retrieval.extraction": {
        "layer": "retrieval",
        "purpose": "Rule-based triple extraction so KAG self-populates from ingestion",
        "exports": ["TripleExtractor"],
    },
    "skeleton.agents.bridge": {
        "layer": "agents",
        "purpose": "MeshBridge: route Coordinator tasks onto the live SwarmMesh",
        "exports": ["MeshBridge"],
    },
    "skeleton.jeeves.matrices": {
        "layer": "jeeves",
        "purpose": "SAM (semantic associations), CLOM (outcome model), KREM (retention decay)",
        "exports": ["SemanticAssociationMap", "CompressedLearnedOutcomeModel", "KnowledgeRetentionMatrix"],
    },
}

GENESIS_HANDLES_ADDED = ["coordinator", "bridge", "ranker"]


def summary() -> Dict[str, Any]:
    return {
        "round4_modules": len(NEW_MODULES),
        "genesis_handles_added": GENESIS_HANDLES_ADDED,
        "kag_self_populating": True,
        "jeeves_matrices": ["sam", "clom", "krem"],
    }
