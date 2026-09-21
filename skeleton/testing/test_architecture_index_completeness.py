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
