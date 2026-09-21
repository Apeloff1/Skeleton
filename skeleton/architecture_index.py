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
    "research_source_catalog": "docs/architecture/research-source-catalog.md",
    "sota_absorb_engine": "docs/architecture/sota-absorb-engine.md",
    "adaptive_absorption_fabric": "docs/architecture/adaptive-absorption-fabric.md",
    "masterplan_gap_audit": "docs/architecture/masterplan-gap-audit.md",
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

CONSTRUCTION_TRACKS = {
    "Q": "research_evidence_substrate",
    "R": "model_and_training_substrate",
    "S": "adaptive_reasoning_test_time_compute",
    "T": "context_compiler_hierarchical_memory",
    "U": "tool_authority_instruction_security",
    "V": "inference_serving_systems",
    "W": "controlled_learning_post_training",
    "X": "evaluation_verification_formal_correctness",
    "Y": "scientific_experiment_promotion_rollback_refresh",
    "Z": "deep_internals_optimizer_control",
    "AA": "rare_massive_upgrades_full_stack_step_changes",
    "AB": "adversarial_foundations_systemic_hardening",
}

PLAN_CHECKPOINTS = {
    "PLAN-20260921-INTERNALS-OPTIMIZERS-MASSIVE-UPGRADES": {
        "created_at": "2026-09-21T21:33:00+02:00",
        "tracks": ("Z", "AA"),
        "implementation_claims_require_signed_evidence": True,
        "production_authority_granted": False,
    },
    "PLAN-20260921-HOSTILE-GAP-AUDIT": {
        "created_at": "2026-09-21",
        "tracks": ("AB",),
        "gap_range": ("G001", "G130"),
        "production_readiness_blocked_by_applicable_open_p0": True,
        "production_authority_granted": False,
    }
}

OPTIMIZER_CONTROL_INVARIANTS = {
    "framework_default_is_authority": False,
    "optimizer_choice_is_versioned_policy": True,
    "parameter_class_mapping_is_explicit": True,
    "checkpoint_binds_optimizer_state": True,
    "promotion_requires_equal_token_and_wallclock_views": True,
    "promotion_requires_failure_recovery_evidence": True,
}

MASSIVE_UPGRADE_INVARIANTS = {
    "microbenchmark_alone_can_promote": False,
    "production_promotion_requires_full_stack_evidence": True,
    "migration_plan_required": True,
    "rollback_plan_required": True,
    "signed_adr_required": True,
    "negative_evidence_is_retained": True,
}

P0_HARDENING_GAPS = (
    "G001_representation_identity",
    "G002_data_lineage",
    "G003_model_artifact_manifest",
    "G004_state_schema_migration",
    "G005_evaluation_firewall",
    "G006_principal_tenant_delegation",
    "G007_execution_sandbox",
    "G008_supply_chain_trust",
    "G009_storage_consistency",
    "G010_leases_fencing_ordering",
    "G011_secret_lifecycle",
    "G012_disaster_recovery",
    "G013_control_plane_isolation",
    "G014_immutable_config_snapshot",
    "G015_unknown_side_effect_reconciliation",
    "G016_deletion_tombstone_propagation",
    "G017_training_poisoning_backdoor_defense",
    "G018_safe_artifact_loading",
    "G019_tamper_evident_audit",
    "G020_safe_mode_break_glass",
    "G084_trust_root_key_compromise_recovery",
)

ADVERSARIAL_HARDENING_INVARIANTS = {
    "open_applicable_p0_blocks_production_readiness": True,
    "model_requires_representation_identity": True,
    "training_checkpoint_requires_data_lineage_root": True,
    "serving_requires_unified_model_artifact_manifest": True,
    "rollback_requires_state_compatibility": True,
    "blind_eval_isolated_from_training_and_search": True,
    "side_effect_requires_authenticated_principal": True,
    "high_risk_execution_requires_sandbox": True,
    "privileged_artifact_load_requires_integrity_verification": True,
    "authoritative_store_declares_consistency_and_restore_semantics": True,
    "distributed_mutation_rejects_stale_writers": True,
    "raw_secrets_are_not_ordinary_prompt_log_or_config_content": True,
    "backup_claim_requires_restore_drill": True,
    "control_plane_has_reserved_recovery_capacity": True,
    "consequential_evidence_binds_immutable_config": True,
    "unknown_irreversible_outcome_is_not_blindly_retried": True,
    "deletion_propagates_to_derived_state": True,
    "training_inputs_are_not_trusted_by_source_reputation_alone": True,
    "untrusted_artifact_load_is_resource_bounded": True,
    "authority_mutations_are_tamper_evident": True,
    "safe_mode_is_required": True,
    "root_trust_key_compromise_has_reroot_recovery": True,
    "authorization_is_revalidated_at_commit": True,
    "signed_objects_use_canonical_serialization": True,
    "distributed_checkpoint_completion_is_manifest_atomic": True,
    "partial_or_speculative_output_is_not_committed_output": True,
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
        "construction_tracks": dict(CONSTRUCTION_TRACKS),
        "plan_checkpoints": {key: dict(value) for key, value in PLAN_CHECKPOINTS.items()},
        "optimizer_control_invariants": dict(OPTIMIZER_CONTROL_INVARIANTS),
        "massive_upgrade_invariants": dict(MASSIVE_UPGRADE_INVARIANTS),
        "p0_hardening_gaps": list(P0_HARDENING_GAPS),
        "adversarial_hardening_invariants": dict(ADVERSARIAL_HARDENING_INVARIANTS),
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
            "Adversarial foundations and systemic hardening construction track",
            "P0 production-readiness blockers for identity, data, artifacts, state, evals, sandboxing, storage, recovery, and audit",
        ],
    }
