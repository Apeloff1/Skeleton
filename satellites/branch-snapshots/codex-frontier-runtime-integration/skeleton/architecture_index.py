"""
Skeleton — Architecture index

Consolidated registry across all build rounds. Import and call
`full_summary()` for the complete picture.
"""

from __future__ import annotations

from typing import Any, Dict

from skeleton import architecture as base
from skeleton import architecture_round3 as r3
from skeleton import architecture_round4 as r4
from skeleton import architecture_round5 as r5
from skeleton import architecture_round6 as r6


GENESIS_PHASES = [
    "kernel",
    "memory",
    "intelligence",
    "swarm",
    "resilience",
    "interface",
    "forge",
    "cortex",
]

ROUNDS = {
    "base": base.architecture_summary(),
    "round3": r3.summary(),
    "round4": r4.summary(),
    "round5": r5.summary(),
    "round6": r6.summary(),
}


def full_summary() -> Dict[str, Any]:
    """Complete architecture summary across all rounds."""
    return {
        "genesis_phases": GENESIS_PHASES,
        "phase_count": len(GENESIS_PHASES),
        "rounds": ROUNDS,
        "key_capabilities": [
            "7+1 phase genesis boot with forge as first-class handle",
            "Four-plane retrieval (vector RAG, CAG, MAG, KAG) with RRF fusion",
            "Self-populating KAG via rule-based triple extraction",
            "LLM provider abstraction (local-echo, OpenAI, Anthropic)",
            "Jeeves memory matrices (SAM, CLOM, KREM)",
            "Godot emit → verify-until-green with bounded repair",
            "Persistence: snapshot/restore for RAG, MAG, KAG, matrices",
            "Swarm-agents bridge (Coordinator tasks on live mesh)",
            "GameForge end-to-end game generation",
            "Developer CLI with 8 commands",
        ],
    }
