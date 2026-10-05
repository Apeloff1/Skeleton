from __future__ import annotations

import pytest

from skeleton.contracts.formal_candidates import (
    FormalCandidate,
    FormalCandidateError,
    FormalModelRef,
    ProofToTestHandoff,
    VerifiedProperty,
    rank_formal_candidates,
)


A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


def candidate(
    candidate_id: str,
    *,
    consequence: int = 5,
    ambiguity: int = 4,
    concurrency: int = 3,
    authority: int = 2,
    recovery: int = 1,
    cost: int = 3,
) -> FormalCandidate:
    return FormalCandidate(
        candidate_id=candidate_id,
        spec_id=f"SPEC.{candidate_id}",
        title=f"Formal candidate {candidate_id}",
        consequence_rank=consequence,
        ambiguity_rank=ambiguity,
        concurrency_ambiguity=concurrency,
        authority_ambiguity=authority,
        recovery_ambiguity=recovery,
        estimated_cost_rank=cost,
        implementation_test_targets=(f"tests::{candidate_id}",),
        assumption_ids=(f"ASSUME.{candidate_id}",),
    )


def model() -> FormalModelRef:
    return FormalModelRef(
        candidate_id="CANDIDATE.A",
        spec_id="SPEC.CANDIDATE.A",
        specification_digest=A,
        implementation_binding_digests=(C, B),
        assumption_digests=(D, A),
    )


def prop(
    ref: FormalModelRef,
    *,
    property_id: str = "PROPERTY.SAFETY",
    candidate_id: str = "CANDIDATE.A",
    assumptions: tuple[str, ...] | None = None,
    test: str = "tests::safety",
) -> VerifiedProperty:
    return VerifiedProperty(
        property_id=property_id,
        candidate_id=candidate_id,
        model_ref_digest=ref.digest,
        proof_result_digest=B,
        proof_status="proved_within_model",
        assumption_digests=assumptions or ref.assumption_digests,
        implementation_test_targets=(test,),
    )


def test_candidate_ranking_prefers_consequence_and_boundary_ambiguity() -> None:
    high = candidate("HIGH", consequence=5, ambiguity=5, concurrency=4)
    low = candidate("LOW", consequence=2, ambiguity=2, concurrency=1, authority=0, recovery=0)
    selected = rank_formal_candidates((low, high), minimum_score=0)
    assert selected == (high, low)
    assert high.selection_score > low.selection_score


def test_candidate_requires_real_concurrency_authority_or_recovery_ambiguity() -> None:
    with pytest.raises(FormalCandidateError, match="must expose"):
        candidate(
            "EMPTY",
            concurrency=0,
            authority=0,
            recovery=0,
        )


def test_candidate_identity_and_budget_inputs_fail_closed() -> None:
    with pytest.raises(FormalCandidateError):
        candidate(" bad ")
    with pytest.raises(FormalCandidateError):
        candidate("BOOL-RANK", consequence=True)
    with pytest.raises(FormalCandidateError):
        rank_formal_candidates((candidate("A"),), maximum_selected=0)


def test_ranking_is_deterministic_and_rejects_duplicate_candidates() -> None:
    first = candidate("A", consequence=4, ambiguity=4)
    second = candidate("B", consequence=4, ambiguity=4)
    assert rank_formal_candidates((second, first), minimum_score=0) == (
        first,
        second,
    )
    with pytest.raises(FormalCandidateError, match="identities"):
        rank_formal_candidates((first, first), minimum_score=0)


def test_model_reference_canonicalizes_binding_and_assumption_order() -> None:
    first = model()
    second = FormalModelRef(
        candidate_id="CANDIDATE.A",
        spec_id="SPEC.CANDIDATE.A",
        specification_digest=A,
        implementation_binding_digests=(B, C),
        assumption_digests=(A, D),
    )
    assert first == second
    assert first.digest == second.digest


def test_model_reference_requires_content_digests() -> None:
    with pytest.raises(FormalCandidateError, match="sha256"):
        FormalModelRef(
            candidate_id="CANDIDATE.A",
            spec_id="SPEC.CANDIDATE.A",
            specification_digest="not-a-digest",
            implementation_binding_digests=(B,),
            assumption_digests=(A,),
        )


def test_handoff_binds_property_to_exact_model_and_assumptions() -> None:
    ref = model()
    handoff = ProofToTestHandoff(ref, (prop(ref),))
    assert handoff.implementation_test_targets == ("tests::safety",)
    assert len(handoff.digest) == 64

    wrong_model = FormalModelRef(
        candidate_id="CANDIDATE.A",
        spec_id="SPEC.CANDIDATE.A",
        specification_digest=B,
        implementation_binding_digests=(B, C),
        assumption_digests=(A, D),
    )
    stale = VerifiedProperty(
        property_id="PROPERTY.STALE",
        candidate_id="CANDIDATE.A",
        model_ref_digest=wrong_model.digest,
        proof_result_digest=B,
        proof_status="proved_within_model",
        assumption_digests=ref.assumption_digests,
        implementation_test_targets=("tests::safety",),
    )
    with pytest.raises(FormalCandidateError, match="stale/different"):
        ProofToTestHandoff(ref, (stale,))


def test_handoff_rejects_assumption_omission() -> None:
    ref = model()
    narrowed = prop(ref, assumptions=(A,))
    with pytest.raises(FormalCandidateError, match="exactly match"):
        ProofToTestHandoff(ref, (narrowed,))


def test_handoff_requires_executable_test_inventory() -> None:
    ref = model()
    handoff = ProofToTestHandoff(
        ref,
        (
            prop(ref, property_id="PROPERTY.A", test="tests::a"),
            prop(ref, property_id="PROPERTY.B", test="tests::b"),
        ),
    )
    handoff.verify_test_inventory(("tests::a", "tests::b", "tests::extra"))
    with pytest.raises(FormalCandidateError, match="unavailable"):
        handoff.verify_test_inventory(("tests::a",))


def test_verified_property_rejects_unscoped_proof_claim() -> None:
    ref = model()
    with pytest.raises(FormalCandidateError, match="scoped"):
        VerifiedProperty(
            property_id="PROPERTY.UNIVERSAL",
            candidate_id="CANDIDATE.A",
            model_ref_digest=ref.digest,
            proof_result_digest=B,
            proof_status="universally_proved",
            assumption_digests=ref.assumption_digests,
            implementation_test_targets=("tests::safety",),
        )


def test_candidate_and_handoff_digests_change_with_evidence() -> None:
    first = candidate("A")
    changed = candidate("A", recovery=2)
    assert first.digest != changed.digest

    ref = model()
    one = ProofToTestHandoff(ref, (prop(ref, test="tests::one"),))
    two = ProofToTestHandoff(ref, (prop(ref, test="tests::two"),))
    assert one.digest != two.digest
