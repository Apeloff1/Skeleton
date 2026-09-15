"""
Skeleton — Round-22 architecture addendum

Foundation round: Merkle DAG content addressing, event journal with
deterministic replay, object-capability security kernel, temporal
invariants — wired as genesis phase 0, the bedrock.
"""

from __future__ import annotations

from typing import Any, Dict


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.foundation.merkle": {
        "layer": "foundation",
        "purpose": "MerkleDAG: content-addressed immutable store with hash-linked provenance, tamper-evident verification, ancestry diff, optional GC",
        "exports": ["MerkleDAG", "DAGAdapter", "Node"],
    },
    "skeleton.foundation.journal": {
        "layer": "foundation",
        "purpose": "EventJournal (append-only hash chain) + ReplayEngine (deterministic reconstruction, time travel) + JournaledBus (transparent capture)",
        "exports": ["EventJournal", "ReplayEngine", "JournaledBus", "JournalEntry"],
    },
    "skeleton.foundation.ocap": {
        "layer": "foundation",
        "purpose": "CapabilityKernel: unforgeable HMAC-chained authority tokens, provably monotonic attenuation, atomic tree revocation, least-authority membrane",
        "exports": ["CapabilityKernel", "Capability", "CapabilityGuard", "Membrane"],
    },
    "skeleton.foundation.temporal": {
        "layer": "foundation",
        "purpose": "TemporalLattice: LTL-lite (always/eventually/never/until/response/precedes) over the journal with violation traces",
        "exports": ["TemporalLattice", "TemporalInvariant", "TemporalEvaluator", "Trace"],
    },
}

BEDROCK_GUARANTEES = [
    "Every artifact hash-addressed: address IS the integrity proof",
    "Every event hash-chained: one flipped byte breaks every link downstream",
    "Every state reconstructible: seed + journal = identical state",
    "Every authority unforgeable and provably attenuable",
    "Every temporal property checkable with evidence traces",
]


def summary() -> Dict[str, Any]:
    return {
        "round22_modules": len(NEW_MODULES),
        "genesis_phases": 12,
        "phase_zero": "foundation",
        "bedrock_guarantees": BEDROCK_GUARANTEES,
        "temporal_operators": ["always", "eventually", "never", "until", "response", "precedes"],
        "genesis_handles_foundation": ["dag", "journal", "replay", "ocap", "membrane", "temporal"],
    }
