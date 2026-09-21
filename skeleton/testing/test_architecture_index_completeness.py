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
    docs = architecture_index.CANONICAL_DOCUMENTS
    tracks = architecture_index.CONSTRUCTION_TRACKS
    gaps = architecture_index.P0_HARDENING_GAPS
    hardening = architecture_index.ADVERSARIAL_HARDENING_INVARIANTS
    checkpoint = architecture_index.PLAN_CHECKPOINTS[
        "PLAN-20260921-HOSTILE-GAP-AUDIT"
    ]

    assert docs["masterplan_gap_audit"] == "docs/architecture/masterplan-gap-audit.md"
    assert tracks["AB"] == "adversarial_foundations_systemic_hardening"
    assert len(gaps) == 21
    assert gaps[0].startswith("G001_")
    assert gaps[-1].startswith("G084_")
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
    assert hardening["root_trust_key_compromise_has_reroot_recovery"] is True
    assert hardening["authorization_is_revalidated_at_commit"] is True
    assert hardening["signed_objects_use_canonical_serialization"] is True
    assert hardening["distributed_checkpoint_completion_is_manifest_atomic"] is True
    assert hardening["partial_or_speculative_output_is_not_committed_output"] is True


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
    assert "G130" in audit
    assert "open P0" in audit
    assert "pairwise" in audit
