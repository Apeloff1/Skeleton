"""
Skeleton — Round-7 architecture addendum

Consolidation round: KREM due-refresh closes the retention loop through
the RepetitionScheduler and DreamEngine; forge becomes a genesis phase.
"""

from __future__ import annotations

from typing import Any, Dict


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.memory.consolidation": {
        "layer": "memory",
        "purpose": "ConsolidationCycle: KREM due() → RepetitionScheduler reviews → DreamEngine themes",
        "exports": ["ConsolidationCycle", "wire_from_genesis"],
    },
}

RETENTION_LOOP = [
    "Jeeves turns feed KREM concepts",
    "KREM retention decays (72h half-life)",
    "due() flags stale concepts",
    "ConsolidationCycle schedules spaced reviews",
    "Refresh re-observes concepts (strength +0.3)",
    "DreamEngine folds episodes into RAG themes",
    "Persistence snapshots the whole memory stack",
]


def summary() -> Dict[str, Any]:
    return {
        "round7_modules": len(NEW_MODULES),
        "retention_loop_stages": len(RETENTION_LOOP),
        "retention_loop": RETENTION_LOOP,
        "genesis_phases": 8,
    }
