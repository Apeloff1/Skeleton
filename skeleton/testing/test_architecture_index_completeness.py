from __future__ import annotations

from skeleton import architecture_index as architecture_index


def test_architecture_index_covers_every_numbered_round() -> None:
    expected = {f"round{number}" for number in range(3, 23)}

    assert set(architecture_index.ROUND_MODULES) == expected
    assert architecture_index.full_summary()["round_count"] == 20
    assert architecture_index.full_summary()["architecture_entry_count"] == 21


def test_architecture_index_exposes_canonical_research_documents() -> None:
    documents = architecture_index.CANONICAL_DOCUMENTS

    assert documents["master_index"] == "docs/ARCHITECTURE_INDEX.md"
    assert documents["build_plan"] == "docs/BUILD_PLAN.md"
    assert (
        documents["research_evidence_evolution"]
        == "docs/architecture/research-evidence-evolution.md"
    )
    assert (
        documents["research_source_catalog"]
        == "docs/architecture/research-source-catalog.md"
    )
    assert documents["sota_absorb_engine"].endswith("sota-absorb-engine.md")
    assert documents["adaptive_absorption_fabric"].endswith(
        "adaptive-absorption-fabric.md"
    )
    assert documents["exotic_architecture_lab"] == "docs/architecture/exotic-architecture-lab.md"
    assert documents["frontier_research_atlas"] == "docs/architecture/frontier-research-atlas-2026.md"
    assert documents["frontier_research_experiment_protocols"] == "docs/architecture/frontier-research-experiment-protocols-2026.md"
    assert documents["research_saturation_checklist"] == "docs/architecture/research-saturation-checklist-2026.md"
    assert documents["research_historical_lineage"] == "docs/architecture/research-historical-lineage.md"
    assert documents["research_source_topology"] == "docs/architecture/research-source-topology.md"


def test_research_evolution_contract_is_fail_closed() -> None:
    contract = architecture_index.EVOLUTION_CONTRACT

    assert contract["research_can_mutate_serving_directly"] is False
    assert (
        contract["production_interactions_can_mutate_deployed_weights_directly"]
        is False
    )
    assert contract["promotion_requires_reproducible_evidence"] is True
    assert contract["promotion_requires_rollback_target"] is True
    assert contract["papers_are_evidence_not_authority"] is True
    assert contract["verifier_score_is_not_truth"] is True


def test_evidence_states_include_negative_and_mixed_results() -> None:
    states = set(architecture_index.EVIDENCE_STATES)

    assert {"foundational", "replicated", "frontier", "emerging"} <= states
    assert {"mixed", "negative", "superseded"} <= states


def test_master_plan_indexes_optimizer_and_massive_upgrade_tracks() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    plan = (root / "docs" / "BUILD_PLAN.md").read_text(encoding="utf-8")
    index = (root / "docs" / "ARCHITECTURE_INDEX.md").read_text(encoding="utf-8")
    catalog = (
        root / "docs" / "architecture" / "research-source-catalog.md"
    ).read_text(encoding="utf-8")
    assert "Track Z — Deep internals and optimizer control plane" in plan
    assert "Track AA — Rare massive upgrades and full-stack step changes" in plan
    assert "**Z** — deep internals and optimizer control plane" in index
    assert "**AA** — rare massive upgrades and full-stack step changes" in index
    assert "Optimizer internals canon and challenger set" in catalog
    assert "Massive-upgrade source seeds" in catalog
    assert "signoff_required_for_implementation_claims: true" in plan
    assert "production_authority_granted: false" in plan


def test_machine_index_exposes_optimizer_and_massive_upgrade_invariants() -> None:
    tracks = architecture_index.CONSTRUCTION_TRACKS
    checkpoint = architecture_index.PLAN_CHECKPOINTS[
        "PLAN-20260921-INTERNALS-OPTIMIZERS-MASSIVE-UPGRADES"
    ]
    optimizer = architecture_index.OPTIMIZER_CONTROL_INVARIANTS
    massive = architecture_index.MASSIVE_UPGRADE_INVARIANTS

    assert tracks["Z"] == "deep_internals_optimizer_control"
    assert tracks["AA"] == "rare_massive_upgrades_full_stack_step_changes"
    assert tuple(checkpoint["tracks"]) == ("Z", "AA")
    assert checkpoint["implementation_claims_require_signed_evidence"] is True
    assert checkpoint["production_authority_granted"] is False

    assert optimizer["framework_default_is_authority"] is False
    assert optimizer["optimizer_choice_is_versioned_policy"] is True
    assert optimizer["parameter_class_mapping_is_explicit"] is True
    assert optimizer["checkpoint_binds_optimizer_state"] is True

    assert massive["microbenchmark_alone_can_promote"] is False
    assert massive["production_promotion_requires_full_stack_evidence"] is True
    assert massive["migration_plan_required"] is True
    assert massive["rollback_plan_required"] is True
    assert massive["signed_adr_required"] is True


def test_hostile_gap_audit_is_machine_visible_and_fail_closed() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    audit = (
        root / "docs" / "architecture" / "masterplan-gap-audit.md"
    ).read_text(encoding="utf-8")
    docs = architecture_index.CANONICAL_DOCUMENTS
    tracks = architecture_index.CONSTRUCTION_TRACKS
    gaps = architecture_index.P0_HARDENING_GAPS
    hardening = architecture_index.ADVERSARIAL_HARDENING_INVARIANTS
    checkpoint = architecture_index.PLAN_CHECKPOINTS[
        "PLAN-20260921-HOSTILE-GAP-AUDIT"
    ]

    assert docs["masterplan_gap_audit"] == "docs/architecture/masterplan-gap-audit.md"
    assert tracks["AB"] == "adversarial_foundations_systemic_hardening"
    assert len(gaps) == 26
    assert gaps[0].startswith("G001_")
    assert gaps[-1].startswith("G193_")
    assert checkpoint["tracks"] == ("AB",)
    assert checkpoint["production_readiness_blocked_by_applicable_open_p0"] is True
    assert checkpoint["production_authority_granted"] is False

    assert hardening["open_applicable_p0_blocks_production_readiness"] is True
    assert hardening["model_requires_representation_identity"] is True
    assert hardening["training_checkpoint_requires_data_lineage_root"] is True
    assert hardening["serving_requires_unified_model_artifact_manifest"] is True
    assert hardening["rollback_requires_state_compatibility"] is True
    assert hardening["blind_eval_isolated_from_training_and_search"] is True
    assert hardening["side_effect_requires_authenticated_principal"] is True
    assert hardening["high_risk_execution_requires_sandbox"] is True
    assert hardening["distributed_mutation_rejects_stale_writers"] is True
    assert hardening["backup_claim_requires_restore_drill"] is True
    assert hardening["safe_mode_is_required"] is True
    assert len(architecture_index.HOSTILE_GAP_IDS) == 200
    for gap_id in architecture_index.HOSTILE_GAP_IDS:
        assert gap_id in audit

    assert hardening["root_trust_key_compromise_has_reroot_recovery"] is True
    assert hardening["authorization_is_revalidated_at_commit"] is True
    assert hardening["signed_objects_use_canonical_serialization"] is True
    assert hardening["distributed_checkpoint_completion_is_manifest_atomic"] is True
    assert hardening["partial_or_speculative_output_is_not_committed_output"] is True
    assert hardening["policy_invariant_precedence_is_deterministic"] is True
    assert hardening["recovery_path_avoids_single_failed_dependency_cycles"] is True
    assert hardening["break_glass_has_dependency_reduced_recovery_path"] is True
    assert hardening["internal_service_identity_is_authenticated"] is True
    assert hardening["restore_reconciles_external_effect_receipts_before_replay"] is True


def test_hostile_gap_audit_and_track_ab_are_canonical_plan_inputs() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    plan = (root / "docs" / "BUILD_PLAN.md").read_text(encoding="utf-8")
    index = (root / "docs" / "ARCHITECTURE_INDEX.md").read_text(encoding="utf-8")
    frontier = (root / "docs" / "FRONTIER_ARCHITECTURE.md").read_text(encoding="utf-8")
    audit = (
        root / "docs" / "architecture" / "masterplan-gap-audit.md"
    ).read_text(encoding="utf-8")

    assert "Track AB — Adversarial foundations and systemic hardening" in plan
    assert "P0 foundations precede exotic optimization" in plan
    assert "**AB** — adversarial foundations and systemic hardening" in index
    assert "Adversarial cross-cutting invariants" in frontier
    assert "G001" in audit
    assert "G200" in audit
    assert "open P0" in audit
    assert "pairwise" in audit


def test_exotic_architecture_lab_is_indexed_and_quarantined() -> None:
    tracks = architecture_index.CONSTRUCTION_TRACKS
    tiers = architecture_index.EXOTIC_ARCHITECTURE_TIERS
    invariants = architecture_index.EXOTIC_ARCHITECTURE_INVARIANTS
    checkpoint = architecture_index.PLAN_CHECKPOINTS[
        "PLAN-20260921-EXOTIC-ARCHITECTURE-LAB"
    ]

    assert tracks["AC"] == "exotic_architecture_laboratory"
    assert tiers["E1"] == tuple(f"AC{number}" for number in range(1, 14))
    assert "AC14" in tiers["E2"]
    assert "AC39" in tiers["E2"]
    assert "AC27" in tiers["E3"]
    assert "AC41" in tiers["E3"]

    assert checkpoint["tracks"] == ("AC",)
    assert checkpoint["production_authority_granted"] is False
    assert checkpoint["promotion_requires_track_ab_p0_closure"] is True

    assert invariants["exotic_candidate_has_falsifiable_hypothesis"] is True
    assert invariants["exotic_candidate_declares_kill_criteria"] is True
    assert invariants["mutable_neural_state_is_not_trusted_durable_memory"] is True
    assert invariants["inference_time_mutation_has_owner_scope_ttl_and_reset"] is True
    assert invariants["tentative_generation_is_not_committed_output"] is True
    assert invariants["exotic_candidate_cannot_execute_tools_from_uncommitted_state"] is True
    assert invariants["compound_exotics_require_component_ablation"] is True
    assert invariants["microbenchmark_only_result_cannot_promote"] is True
    assert invariants["architecture_search_cannot_self_promote"] is True
    assert invariants["track_ab_p0_invariants_remain_binding"] is True
    assert invariants["promotion_to_production_requires_track_aa_path"] is True


def test_exotic_plan_and_research_canon_are_canonical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    plan = (root / "docs" / "BUILD_PLAN.md").read_text(encoding="utf-8")
    index = (root / "docs" / "ARCHITECTURE_INDEX.md").read_text(encoding="utf-8")
    catalog = (
        root / "docs" / "architecture" / "research-source-catalog.md"
    ).read_text(encoding="utf-8")
    manual = (
        root / "docs" / "architecture" / "exotic-architecture-lab.md"
    ).read_text(encoding="utf-8")

    assert "Track AC — Exotic architecture laboratory" in plan
    assert "AC44. Exotic promotion ladder" in plan
    assert "**AC** — exotic architecture laboratory" in index
    assert "Exotic architecture canon" in catalog
    assert "Titans: Learning to Memorize at Test Time" in catalog
    assert "Byte Latent Transformer" in catalog
    assert "Discrete Diffusion" in catalog
    assert "Recurrent Depth" in catalog
    assert "Universal YOCO" in catalog
    assert "BitNet" in catalog
    assert "Track AC anti-canon" in catalog
    assert "Architecture coordinate system" in manual
    assert "ExoticCandidate manifest" in manual
    assert "Mutable neural state protocol" in manual
    assert "Exotic falsification battery" in manual
    assert "There is no AC → production shortcut." in manual


def test_frontier_research_saturation_is_machine_visible() -> None:
    tracks = architecture_index.CONSTRUCTION_TRACKS
    checkpoint = architecture_index.PLAN_CHECKPOINTS[
        "PLAN-20260921-FRONTIER-RESEARCH-SATURATION"
    ]
    invariants = architecture_index.RESEARCH_PASS_INVARIANTS
    source_audit = architecture_index.RESEARCH_SOURCE_AUDIT_INVARIANTS
    automation = architecture_index.RESEARCH_AUTOMATION_INVARIANTS
    monitorability = architecture_index.MONITORABILITY_RESEARCH_INVARIANTS
    debt = architecture_index.RESEARCH_DEBT_INVARIANTS
    rigor = architecture_index.RESEARCH_EXPERIMENT_RIGOR_INVARIANTS
    coverage = architecture_index.RESEARCH_DOMAIN_COVERAGE_REQUIREMENTS
    measurement = architecture_index.RESEARCH_MEASUREMENT_INVARIANTS

    assert tracks["AD"] == "research_saturation_replication_frontier_synthesis"
    assert checkpoint["tracks"] == ("AD",)
    assert checkpoint["research_conclusion_range"] == ("FR001", "FR114")
    assert checkpoint["research_question_range"] == ("RQ001", "RQ067")
    assert checkpoint["source_verification_range"] == ("SV001", "SV055")
    assert checkpoint["frontier_delta_range"] == ("FD001", "FD021")
    assert checkpoint["contradiction_range"] == ("CX001", "CX024")
    assert checkpoint["research_debt_range"] == ("RDE001", "RDE036")
    assert checkpoint["experiment_protocol_range"] == ("RXP001", "RXP035")
    assert checkpoint["production_authority_granted"] is False
    assert checkpoint["research_refresh_required"] is True

    assert len(architecture_index.RESEARCH_CONCLUSION_IDS) == 114
    assert len(architecture_index.RESEARCH_QUESTION_IDS) == 67
    assert len(architecture_index.RESEARCH_SOURCE_VERIFICATION_IDS) == 55
    assert len(architecture_index.FRONTIER_DELTA_IDS) == 21
    assert len(architecture_index.RESEARCH_CONTRADICTION_IDS) == 24
    assert len(architecture_index.RESEARCH_DEBT_IDS) == 36
    assert len(architecture_index.RESEARCH_EXPERIMENT_PROTOCOL_IDS) == 35
    assert len(architecture_index.FRONTIER_RESEARCH_DOMAINS) == 19

    assert invariants["research_source_is_evidence_not_authority"] is True
    assert invariants["contradictory_evidence_is_retained"] is True
    assert invariants["negative_results_are_first_class"] is True
    assert invariants["paper_status_is_preserved"] is True
    assert invariants["scale_transfer_is_measured_not_assumed"] is True
    assert invariants["research_agent_cannot_self_validate"] is True

    assert source_audit["accepted_and_submitted_are_not_equivalent"] is True
    assert source_audit["withdrawn_work_remains_available_as_scoped_evidence"] is True
    assert source_audit["first_party_evidence_is_not_independent_consensus"] is True
    assert source_audit["status_upgrade_is_new_evidence_event"] is True
    assert source_audit["correction_or_retraction_is_new_evidence_event"] is True
    assert "accepted_peer_reviewed" in architecture_index.RESEARCH_SOURCE_STATUS_STATES
    assert "accepted_poster" in architecture_index.RESEARCH_SOURCE_STATUS_STATES
    assert "accepted_oral" in architecture_index.RESEARCH_SOURCE_STATUS_STATES
    assert "workshop" in architecture_index.RESEARCH_SOURCE_STATUS_STATES
    assert "submission" in architecture_index.RESEARCH_SOURCE_STATUS_STATES
    assert "arr_submission" in architecture_index.RESEARCH_SOURCE_STATUS_STATES
    assert "withdrawn" in architecture_index.RESEARCH_SOURCE_STATUS_STATES
    assert "rejected" in architecture_index.RESEARCH_SOURCE_STATUS_STATES
    assert "corrected" in architecture_index.RESEARCH_SOURCE_STATUS_STATES
    assert "retracted" in architecture_index.RESEARCH_SOURCE_STATUS_STATES

    assert automation["research_agent_cannot_mark_own_result_reproduced"] is True
    assert automation["research_agent_cannot_read_blind_promotion_answers"] is True
    assert automation["scorer_variance_cannot_be_exploited_as_success"] is True
    assert automation["research_agent_result_requires_independent_recompute_or_review"] is True

    assert monitorability["monitorability_is_versioned_measured_property"] is True
    assert monitorability["monitorability_is_not_assumed_monotonic_with_capability"] is True
    assert monitorability["learned_detector_ood_generalization_is_not_assumed"] is True

    assert "paper_scale" in architecture_index.REPRODUCTION_CLASSES
    assert "transfer" in architecture_index.REPRODUCTION_CLASSES
    assert "systems" in architecture_index.REPRODUCTION_CLASSES
    assert "adversarial" in architecture_index.REPRODUCTION_CLASSES
    assert "open" in architecture_index.RESEARCH_DEBT_STATES
    assert "partially_retired" in architecture_index.RESEARCH_DEBT_STATES
    assert "supported_in_scope" in architecture_index.RESEARCH_RESULT_STATES
    assert "null_result" in architecture_index.RESEARCH_RESULT_STATES
    assert "falsified_in_scope" in architecture_index.RESEARCH_RESULT_STATES
    assert "reproduction_failed" in architecture_index.RESEARCH_RESULT_STATES

    assert debt["open_research_debt_is_visible"] is True
    assert debt["paper_claim_alone_cannot_retire_local_debt"] is True
    assert debt["failed_reproduction_is_retained"] is True
    assert debt["production_claim_lists_dependent_open_debt"] is True

    assert rigor["selection_and_tuning_budget_is_recorded"] is True
    assert rigor["failed_and_diverged_runs_are_not_silently_dropped"] is True
    assert rigor["baseline_receives_comparable_tuning_and_kernels"] is True
    assert rigor["multiple_comparisons_are_recorded"] is True
    assert rigor["single_seed_is_not_zero_uncertainty"] is True

    assert coverage["foundational_anchor"] is True
    assert coverage["current_frontier_source"] is True
    assert coverage["negative_or_counterevidence"] is True
    assert coverage["verified_source_status"] is True
    assert coverage["mandatory_baseline"] is True
    assert coverage["local_experiment_protocol"] is True
    assert coverage["research_debt_assessment"] is True
    assert coverage["refresh_trigger"] is True

    assert measurement["practical_significance_is_reported"] is True
    assert measurement["cold_and_warm_paths_are_separated"] is True
    assert measurement["tail_latency_and_failure_rate_are_reported"] is True
    assert measurement["missing_results_are_not_silently_removed"] is True
    assert measurement["hard_floors_dominate_aggregate_score"] is True
    assert measurement["blind_benchmark_access_is_audited"] is True
    assert measurement["analysis_outputs_are_traceable_to_result_bundles"] is True
    assert measurement["expensive_experiment_has_decision_value_statement"] is True


def test_frontier_research_atlas_has_complete_reference_namespaces() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    atlas = (
        root / "docs" / "architecture" / "frontier-research-atlas-2026.md"
    ).read_text(encoding="utf-8")
    protocols = (
        root
        / "docs"
        / "architecture"
        / "frontier-research-experiment-protocols-2026.md"
    ).read_text(encoding="utf-8")
    plan = (root / "docs" / "BUILD_PLAN.md").read_text(encoding="utf-8")
    index = (root / "docs" / "ARCHITECTURE_INDEX.md").read_text(encoding="utf-8")

    assert architecture_index.CANONICAL_DOCUMENTS["frontier_research_atlas"] == (
        "docs/architecture/frontier-research-atlas-2026.md"
    )
    assert "Track AD — Research saturation, replication, and frontier synthesis" in plan
    assert "**AD** — research saturation, replication, and frontier synthesis" in index
    assert "Source-status verification audit" in atlas
    assert "September 2026 frontier delta" in atlas
    assert "Domain evidence matrix" in atlas
    assert "Contradiction and tension ledger" in atlas
    assert "Research debt ledger" in atlas
    assert "Statistical and experimental rigor contract" in atlas
    assert "Research freshness tiers" in atlas
    assert "Experiment sequencing policy" in protocols
    assert "Experiment-result decision vocabulary" in protocols
    assert "Experiment integrity gate" in protocols

    for finding_id in architecture_index.RESEARCH_CONCLUSION_IDS:
        assert finding_id in atlas
    for question_id in architecture_index.RESEARCH_QUESTION_IDS:
        assert question_id in atlas
    for source_id in architecture_index.RESEARCH_SOURCE_VERIFICATION_IDS:
        assert source_id in atlas
    for delta_id in architecture_index.FRONTIER_DELTA_IDS:
        assert delta_id in atlas
    for contradiction_id in architecture_index.RESEARCH_CONTRADICTION_IDS:
        assert contradiction_id in atlas
    for debt_id in architecture_index.RESEARCH_DEBT_IDS:
        assert debt_id in atlas
    for protocol_id in architecture_index.RESEARCH_EXPERIMENT_PROTOCOL_IDS:
        assert protocol_id in protocols

    assert "RExBench" in atlas and "WITHDRAWN" in atlas
    assert "ToolTweak" in atlas and "SUBMISSION" in atlas
    assert "SWE-Bench Pro" in atlas and "SUBMISSION" in atlas
    assert "Aletheia" in atlas and "ACL ARR 2026 March SUBMISSION" in atlas
    assert "MemGAS" in atlas and "ICLR 2026 Poster" in atlas
    assert "Data Mixture Optimization" in atlas and "NeurIPS 2025 Poster" in atlas
    assert "To Infinity and Beyond" in atlas and "ICLR 2026 Oral" in atlas
    assert "research agent cannot mark its own result reproduced" in atlas.lower()
    assert "AD60. Debt retirement and reopening" in plan
    assert "AD65. Research experiment sequencing" in plan
    assert "AD72. Experiment decision-value review" in plan
    assert "AD81. Domain-resolved question bank" in plan
    assert "FD001–FD021" in plan


def test_research_saturation_accountability_distinguishes_planning_from_reproduction() -> None:
    from pathlib import Path

    checkpoint = architecture_index.PLAN_CHECKPOINTS[
        "PLAN-20260921-RESEARCH-SATURATION-ACCOUNTABILITY"
    ]

    assert checkpoint["tracks"] == ("AD",)
    assert checkpoint["domain_count"] == 19
    assert checkpoint["planning_status"] == "planning_covered"
    assert checkpoint["local_reproduction_status"] == "reproduction_pending"
    assert checkpoint["production_authority_granted"] is False
    assert checkpoint["signoff_required_for_reproduction_claims"] is True
    assert checkpoint["signoff_required_for_production_claims"] is True

    root = Path(__file__).resolve().parents[2]
    checklist = (
        root / "docs" / "architecture" / "research-saturation-checklist-2026.md"
    ).read_text(encoding="utf-8")

    assert "PLANNING_COVERED" in checklist
    assert "REPRODUCTION_PENDING" in checklist
    assert "No domain in this checklist is upgraded to production evidence" in checklist
    assert "signoff_required_for_reproduction_claims: true" in checklist
    assert "signoff_required_for_production_claims: true" in checklist


def test_historical_lineage_and_source_topology_are_complete() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    lineage = (
        root / "docs" / "architecture" / "research-historical-lineage.md"
    ).read_text(encoding="utf-8")
    topology = (
        root / "docs" / "architecture" / "research-source-topology.md"
    ).read_text(encoding="utf-8")
    plan = (root / "docs" / "BUILD_PLAN.md").read_text(encoding="utf-8")

    assert len(architecture_index.HISTORICAL_RESEARCH_LINEAGE_IDS) == 110
    assert len(architecture_index.RESEARCH_SOURCE_FAMILY_IDS) == 55

    for lineage_id in architecture_index.HISTORICAL_RESEARCH_LINEAGE_IDS:
        assert lineage_id in lineage
    for source_id in architecture_index.RESEARCH_SOURCE_FAMILY_IDS:
        assert source_id in topology

    historical = architecture_index.PLAN_CHECKPOINTS[
        "PLAN-20260921-HISTORICAL-RESEARCH-LINEAGE"
    ]
    source_topology = architecture_index.PLAN_CHECKPOINTS[
        "PLAN-20260921-RESEARCH-SOURCE-TOPOLOGY"
    ]

    assert historical["historical_anchor_range"] == ("HL001", "HL110")
    assert historical["production_authority_granted"] is False
    assert source_topology["source_family_range"] == ("RS001", "RS055")
    assert source_topology["source_adapters_are_evidence_retrieval_only"] is True
    assert source_topology["production_authority_granted"] is False

    assert "AD73. Historical cross-discipline lineage gate" in plan
    assert "AD80. Source disappearance and archival resilience" in plan
