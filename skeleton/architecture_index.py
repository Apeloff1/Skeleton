"""
Skeleton — Architecture index

Canonical machine-readable registry across the base architecture, every
numbered architecture round, and the documents that govern current
construction/evolution.

Import and call `full_summary()` for the complete picture.
"""

from __future__ import annotations

from typing import Any, Dict

from skeleton import architecture as base
from skeleton import architecture_round3 as r3
from skeleton import architecture_round4 as r4
from skeleton import architecture_round5 as r5
from skeleton import architecture_round6 as r6
from skeleton import architecture_round7 as r7
from skeleton import architecture_round8 as r8
from skeleton import architecture_round9 as r9
from skeleton import architecture_round10 as r10
from skeleton import architecture_round11 as r11
from skeleton import architecture_round12 as r12
from skeleton import architecture_round13 as r13
from skeleton import architecture_round14 as r14
from skeleton import architecture_round15 as r15
from skeleton import architecture_round16 as r16
from skeleton import architecture_round17 as r17
from skeleton import architecture_round18 as r18
from skeleton import architecture_round19 as r19
from skeleton import architecture_round20 as r20
from skeleton import architecture_round21 as r21
from skeleton import architecture_round22 as r22


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

ROUND_MODULES = {
    "round3": r3,
    "round4": r4,
    "round5": r5,
    "round6": r6,
    "round7": r7,
    "round8": r8,
    "round9": r9,
    "round10": r10,
    "round11": r11,
    "round12": r12,
    "round13": r13,
    "round14": r14,
    "round15": r15,
    "round16": r16,
    "round17": r17,
    "round18": r18,
    "round19": r19,
    "round20": r20,
    "round21": r21,
    "round22": r22,
}

ROUNDS = {
    "base": base.architecture_summary(),
    **{name: module.summary() for name, module in ROUND_MODULES.items()},
}

CANONICAL_DOCUMENTS = {
    "master_index": "docs/ARCHITECTURE_INDEX.md",
    "architecture": "docs/ARCHITECTURE.md",
    "frontier_contract": "docs/FRONTIER_ARCHITECTURE.md",
    "build_plan": "docs/BUILD_PLAN.md",
    "research_evidence_evolution": "docs/architecture/research-evidence-evolution.md",
    "sota_absorb_engine": "docs/architecture/sota-absorb-engine.md",
    "adaptive_absorption_fabric": "docs/architecture/adaptive-absorption-fabric.md",
}

EVIDENCE_STATES = (
    "foundational",
    "replicated",
    "frontier",
    "emerging",
    "mixed",
    "negative",
    "superseded",
)

RESEARCH_PROMOTION_STAGES = (
    "discovered",
    "normalized",
    "triaged",
    "reproduction_pending",
    "reproduced",
    "prototyped",
    "benchmarked",
    "challenged",
    "adr_accepted",
    "shadow",
    "canary",
    "promoted",
)

RESEARCH_TERMINAL_OR_SIDE_STATES = (
    "reproduction_failed",
    "rejected",
    "contested",
    "superseded",
    "retracted",
    "quarantined",
)

EVOLUTION_CONTRACT = {
    "research_can_mutate_serving_directly": False,
    "production_interactions_can_mutate_deployed_weights_directly": False,
    "promotion_requires_reproducible_evidence": True,
    "promotion_requires_rollback_target": True,
    "serving_reads_promoted_state": True,
    "papers_are_evidence_not_authority": True,
    "verifier_score_is_not_truth": True,
}


def full_summary() -> Dict[str, Any]:
    """Return the complete architecture summary across all indexed rounds."""
    return {
        "architecture_version": base.ARCHITECTURE_VERSION,
        "genesis_phases": GENESIS_PHASES,
        "phase_count": len(GENESIS_PHASES),
        "rounds": ROUNDS,
        "round_count": len(ROUND_MODULES),
        "architecture_entry_count": len(ROUNDS),
        "canonical_documents": dict(CANONICAL_DOCUMENTS),
        "evidence_states": list(EVIDENCE_STATES),
        "research_promotion_stages": list(RESEARCH_PROMOTION_STAGES),
        "research_side_states": list(RESEARCH_TERMINAL_OR_SIDE_STATES),
        "evolution_contract": dict(EVOLUTION_CONTRACT),
        "key_capabilities": [
            "7+1 phase genesis boot with forge as first-class handle",
            "Complete indexed architecture history: base plus rounds 3 through 22",
            "Four-plane retrieval (vector RAG, CAG, MAG, KAG) with RRF fusion",
            "Self-populating KAG via rule-based triple extraction",
            "LLM provider abstraction (local-echo, OpenAI, Anthropic)",
            "Jeeves memory matrices (SAM, CLOM, KREM)",
            "Godot emit → verify-until-green with bounded repair",
            "Persistence: snapshot/restore for RAG, MAG, KAG, matrices",
            "Swarm-agents bridge (Coordinator tasks on live mesh)",
            "GameForge end-to-end game generation",
            "Developer CLI with 8 commands",
            "Research evidence maturity and provenance contract",
            "Paper-to-experiment-to-shadow-to-canary promotion path",
            "Serving-isolated knowledge absorption with immutable snapshots",
            "Adaptive reasoning/test-time-compute construction track",
            "Model-family-neutral dense, SSM, hybrid, and MoE construction target",
            "Hierarchical working, episodic, semantic, and procedural memory target",
            "Tool intent, validation, authority, execution, and receipt boundary",
            "Plural verification with explicit verifier independence metadata",
            "Controlled fast, medium, and slow adaptation velocities",
        ],
    }
