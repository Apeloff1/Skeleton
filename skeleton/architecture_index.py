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
    "exotic_architecture_lab": "docs/architecture/exotic-architecture-lab.md",
    "frontier_research_atlas": "docs/architecture/frontier-research-atlas-2026.md",
    "frontier_research_experiment_protocols": "docs/architecture/frontier-research-experiment-protocols-2026.md",
    "research_saturation_checklist": "docs/architecture/research-saturation-checklist-2026.md",
    "research_historical_lineage": "docs/architecture/research-historical-lineage.md",
    "research_source_topology": "docs/architecture/research-source-topology.md",
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
    "AC": "exotic_architecture_laboratory",
    "AD": "research_saturation_replication_frontier_synthesis",
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
        "gap_range": ("G001", "G200"),
        "production_readiness_blocked_by_applicable_open_p0": True,
        "production_authority_granted": False,
    },
    "PLAN-20260921-EXOTIC-ARCHITECTURE-LAB": {
        "created_at": "2026-09-21",
        "tracks": ("AC",),
        "tier_e1_range": ("AC1", "AC13"),
        "tier_e2_ranges": (("AC14", "AC26"), ("AC31", "AC39")),
        "tier_e3_ranges": (("AC27", "AC30"), ("AC40", "AC41")),
        "production_authority_granted": False,
        "promotion_requires_track_ab_p0_closure": True,
    },
    "PLAN-20260921-FRONTIER-RESEARCH-SATURATION": {
        "created_at": "2026-09-21",
        "tracks": ("AD",),
        "research_conclusion_range": ("FR001", "FR114"),
        "research_question_range": ("RQ001", "RQ010"),
        "source_verification_range": ("SV001", "SV055"),
        "frontier_delta_range": ("FD001", "FD021"),
        "contradiction_range": ("CX001", "CX024"),
        "research_debt_range": ("RDE001", "RDE036"),
        "experiment_protocol_range": ("RXP001", "RXP035"),
        "production_authority_granted": False,
        "research_refresh_required": True,
    },
    "PLAN-20260921-RESEARCH-SOURCE-TOPOLOGY": {
        "created_at": "2026-09-21",
        "tracks": ("AD",),
        "source_family_range": ("RS001", "RS055"),
        "source_adapters_are_evidence_retrieval_only": True,
        "production_authority_granted": False,
    },
    "PLAN-20260921-HISTORICAL-RESEARCH-LINEAGE": {
        "created_at": "2026-09-21",
        "tracks": ("AD",),
        "historical_anchor_range": ("HL001", "HL110"),
        "production_authority_granted": False,
    },
    "PLAN-20260921-RESEARCH-SATURATION-ACCOUNTABILITY": {
        "created_at": "2026-09-21T22:39:00+02:00",
        "tracks": ("AD",),
        "domain_count": 19,
        "planning_status": "planning_covered",
        "local_reproduction_status": "reproduction_pending",
        "production_authority_granted": False,
        "signoff_required_for_reproduction_claims": True,
        "signoff_required_for_production_claims": True,
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

HOSTILE_GAP_IDS = tuple(f"G{number:03d}" for number in range(1, 201))

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
    "G131_policy_invariant_conflict_resolution",
    "G135_recovery_dependency_cycle",
    "G136_break_glass_dependency_independence",
    "G161_internal_service_identity",
    "G193_restore_external_effect_reconciliation",
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
    "policy_invariant_precedence_is_deterministic": True,
    "recovery_path_avoids_single_failed_dependency_cycles": True,
    "break_glass_has_dependency_reduced_recovery_path": True,
    "internal_service_identity_is_authenticated": True,
    "restore_reconciles_external_effect_receipts_before_replay": True,
}

EXOTIC_ARCHITECTURE_TIERS = {
    "E1": tuple(f"AC{number}" for number in range(1, 14)),
    "E2": tuple(
        [f"AC{number}" for number in range(14, 27)]
        + [f"AC{number}" for number in range(31, 40)]
    ),
    "E3": tuple(
        [f"AC{number}" for number in range(27, 31)]
        + [f"AC{number}" for number in range(40, 42)]
    ),
}

EXOTIC_ARCHITECTURE_INVARIANTS = {
    "exotic_candidate_has_falsifiable_hypothesis": True,
    "exotic_candidate_declares_kill_criteria": True,
    "mutable_neural_state_is_not_trusted_durable_memory": True,
    "inference_time_mutation_has_owner_scope_ttl_and_reset": True,
    "tentative_generation_is_not_committed_output": True,
    "exotic_candidate_cannot_execute_tools_from_uncommitted_state": True,
    "compound_exotics_require_component_ablation": True,
    "microbenchmark_only_result_cannot_promote": True,
    "architecture_search_cannot_self_promote": True,
    "track_ab_p0_invariants_remain_binding": True,
    "promotion_to_production_requires_track_aa_path": True,
}

FRONTIER_RESEARCH_DOMAINS = (
    "model_architecture",
    "representation_tokenization",
    "neural_memory_retrieval",
    "training_data_mixtures",
    "optimization_numerics",
    "test_time_reasoning",
    "formal_reasoning_verification",
    "agents_long_horizon",
    "agent_memory_procedures",
    "serving_inference",
    "distributed_training",
    "multimodal_world_models",
    "evaluation_science",
    "safety_security_monitorability",
    "interpretability",
    "uncertainty_calibration",
    "continual_adaptation",
    "hardware_precision_efficiency",
    "research_automation",
)

RESEARCH_PASS_INVARIANTS = {
    "research_source_is_evidence_not_authority": True,
    "research_conclusion_is_scoped": True,
    "research_conclusion_records_confidence": True,
    "contradictory_evidence_is_retained": True,
    "negative_results_are_first_class": True,
    "paper_status_is_preserved": True,
    "reproduction_class_is_explicit": True,
    "baseline_parity_is_required_for_promotion_evidence": True,
    "equal_resource_views_are_plural": True,
    "scale_transfer_is_measured_not_assumed": True,
    "hardware_transfer_is_measured_not_assumed": True,
    "inference_protocol_is_part_of_reasoning_eval": True,
    "synthetic_data_ancestry_is_tracked": True,
    "verifier_independence_is_measured": True,
    "research_agent_cannot_self_validate": True,
    "blind_holdout_is_not_research_selection_metric": True,
    "research_refresh_is_required": True,
    "research_cannot_directly_mutate_production": True,
}

RESEARCH_CONCLUSION_IDS = tuple(f"FR{number:03d}" for number in range(1, 115))
RESEARCH_QUESTION_IDS = tuple(f"RQ{number:03d}" for number in range(1, 11))
RESEARCH_SOURCE_VERIFICATION_IDS = tuple(f"SV{number:03d}" for number in range(1, 56))
FRONTIER_DELTA_IDS = tuple(f"FD{number:03d}" for number in range(1, 22))
RESEARCH_CONTRADICTION_IDS = tuple(f"CX{number:03d}" for number in range(1, 25))
RESEARCH_DEBT_IDS = tuple(f"RDE{number:03d}" for number in range(1, 37))
RESEARCH_EXPERIMENT_PROTOCOL_IDS = tuple(f"RXP{number:03d}" for number in range(1, 36))
HISTORICAL_RESEARCH_LINEAGE_IDS = tuple(f"HL{number:03d}" for number in range(1, 111))
RESEARCH_SOURCE_FAMILY_IDS = tuple(f"RS{number:03d}" for number in range(1, 56))

RESEARCH_SOURCE_STATUS_STATES = (
    "accepted_peer_reviewed",
    "accepted_poster",
    "accepted_oral",
    "workshop",
    "preprint",
    "submission",
    "arr_submission",
    "withdrawn",
    "rejected",
    "official_org_evidence",
    "corrected",
    "retracted",
    "status_unresolved",
)

REPRODUCTION_CLASSES = (
    "sanity",
    "paper_scale",
    "transfer",
    "systems",
    "adversarial",
    "negative",
    "independent",
)

RESEARCH_DEBT_STATES = (
    "open",
    "experiment_designed",
    "running",
    "evidence_collected",
    "challenged",
    "retired",
    "partially_retired",
    "invalidated",
    "deferred",
)

RESEARCH_RESULT_STATES = (
    "supported_in_scope",
    "partially_supported",
    "null_result",
    "falsified_in_scope",
    "inconclusive_variance",
    "inconclusive_resource_limit",
    "invalid_method",
    "invalid_baseline",
    "invalid_evaluation",
    "reproduction_failed",
)

RESEARCH_SOURCE_AUDIT_INVARIANTS = {
    "source_existence_is_verified": True,
    "venue_or_submission_status_is_preserved": True,
    "source_version_and_date_are_preserved": True,
    "accepted_and_submitted_are_not_equivalent": True,
    "withdrawn_work_remains_available_as_scoped_evidence": True,
    "first_party_evidence_is_not_independent_consensus": True,
    "status_upgrade_is_new_evidence_event": True,
    "correction_or_retraction_is_new_evidence_event": True,
    "source_claim_scope_is_preserved": True,
    "research_status_cannot_be_inferred_from_title_or_recency": True,
}

RESEARCH_AUTOMATION_INVARIANTS = {
    "research_agent_cannot_mark_own_result_reproduced": True,
    "research_agent_cannot_read_blind_promotion_answers": True,
    "research_agent_trajectory_is_auditable": True,
    "research_agent_generated_training_data_has_provenance": True,
    "research_agent_experiment_uses_immutable_manifest": True,
    "scorer_variance_cannot_be_exploited_as_success": True,
    "research_agent_code_runs_in_sandbox": True,
    "research_agent_result_requires_independent_recompute_or_review": True,
}

MONITORABILITY_RESEARCH_INVARIANTS = {
    "monitorability_is_versioned_measured_property": True,
    "monitorability_is_not_assumed_monotonic_with_capability": True,
    "monitorability_is_revalidated_after_training_changes": True,
    "trajectory_monitoring_does_not_replace_deterministic_authority": True,
    "learned_detector_ood_generalization_is_not_assumed": True,
}

RESEARCH_DEBT_INVARIANTS = {
    "open_research_debt_is_visible": True,
    "paper_claim_alone_cannot_retire_local_debt": True,
    "toy_reproduction_does_not_imply_scale_transfer": True,
    "failed_reproduction_is_retained": True,
    "partial_retirement_records_scope": True,
    "retired_debt_can_reopen_after_material_change": True,
    "production_claim_lists_dependent_open_debt": True,
}

RESEARCH_EXPERIMENT_RIGOR_INVARIANTS = {
    "selection_and_tuning_budget_is_recorded": True,
    "failed_and_diverged_runs_are_not_silently_dropped": True,
    "baseline_receives_comparable_tuning_and_kernels": True,
    "multiple_comparisons_are_recorded": True,
    "lifecycle_cost_is_reported_when_material": True,
    "negative_space_and_untested_scope_are_recorded": True,
    "single_seed_is_not_zero_uncertainty": True,
}

RESEARCH_DOMAIN_COVERAGE_REQUIREMENTS = {
    "foundational_anchor": True,
    "current_frontier_source": True,
    "negative_or_counterevidence": True,
    "verified_source_status": True,
    "mandatory_baseline": True,
    "local_experiment_protocol": True,
    "research_debt_assessment": True,
    "scale_and_hardware_scope": True,
    "unresolved_contradictions": True,
    "refresh_trigger": True,
}

RESEARCH_MEASUREMENT_INVARIANTS = {
    "practical_significance_is_reported": True,
    "paired_comparisons_are_preferred_when_available": True,
    "benchmark_results_are_stratified_when_material": True,
    "cold_and_warm_paths_are_separated": True,
    "tail_latency_and_failure_rate_are_reported": True,
    "metric_sensitivity_is_recorded": True,
    "missing_results_are_not_silently_removed": True,
    "hard_floors_dominate_aggregate_score": True,
    "blind_benchmark_access_is_audited": True,
    "analysis_outputs_are_traceable_to_result_bundles": True,
    "expensive_experiment_has_decision_value_statement": True,
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
        "hostile_gap_ids": list(HOSTILE_GAP_IDS),
        "p0_hardening_gaps": list(P0_HARDENING_GAPS),
        "adversarial_hardening_invariants": dict(ADVERSARIAL_HARDENING_INVARIANTS),
        "exotic_architecture_tiers": {key: list(value) for key, value in EXOTIC_ARCHITECTURE_TIERS.items()},
        "exotic_architecture_invariants": dict(EXOTIC_ARCHITECTURE_INVARIANTS),
        "frontier_research_domains": list(FRONTIER_RESEARCH_DOMAINS),
        "research_pass_invariants": dict(RESEARCH_PASS_INVARIANTS),
        "research_conclusion_ids": list(RESEARCH_CONCLUSION_IDS),
        "research_question_ids": list(RESEARCH_QUESTION_IDS),
        "research_source_verification_ids": list(RESEARCH_SOURCE_VERIFICATION_IDS),
        "frontier_delta_ids": list(FRONTIER_DELTA_IDS),
        "research_contradiction_ids": list(RESEARCH_CONTRADICTION_IDS),
        "research_debt_ids": list(RESEARCH_DEBT_IDS),
        "research_experiment_protocol_ids": list(RESEARCH_EXPERIMENT_PROTOCOL_IDS),
        "historical_research_lineage_ids": list(HISTORICAL_RESEARCH_LINEAGE_IDS),
        "research_source_family_ids": list(RESEARCH_SOURCE_FAMILY_IDS),
        "research_source_status_states": list(RESEARCH_SOURCE_STATUS_STATES),
        "reproduction_classes": list(REPRODUCTION_CLASSES),
        "research_debt_states": list(RESEARCH_DEBT_STATES),
        "research_result_states": list(RESEARCH_RESULT_STATES),
        "research_source_audit_invariants": dict(RESEARCH_SOURCE_AUDIT_INVARIANTS),
        "research_automation_invariants": dict(RESEARCH_AUTOMATION_INVARIANTS),
        "monitorability_research_invariants": dict(MONITORABILITY_RESEARCH_INVARIANTS),
        "research_debt_invariants": dict(RESEARCH_DEBT_INVARIANTS),
        "research_experiment_rigor_invariants": dict(RESEARCH_EXPERIMENT_RIGOR_INVARIANTS),
        "research_domain_coverage_requirements": dict(RESEARCH_DOMAIN_COVERAGE_REQUIREMENTS),
        "research_measurement_invariants": dict(RESEARCH_MEASUREMENT_INVARIANTS),
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
            "Quarantined exotic architecture laboratory with falsification and kill criteria",
            "Test-time neural memory, byte-latent, diffusion, recurrent-depth, equilibrium, sparse/ternary and latent-multimodal candidate families",
            "Frontier research saturation with scoped conclusions and contradiction tracking",
            "Research reproduction classes, equal-resource normalization, scale-transfer and negative-evidence retention",
            "Source-status verification with accepted/preprint/submission/withdrawn distinctions",
            "Versioned monitorability research and trajectory-level agent safety evidence",
            "Research-agent anti-cheating, independent recomputation, and blind-eval isolation",
        ],
    }
