from dataclasses import replace

from core.truth_verifier import (
    EvidenceItem,
    EvidenceKind,
    TruthVerifier,
    VerificationState,
    verify_claim_attestation,
)


def ev(source, group, *, kind=EvidenceKind.PRIMARY_EMPIRICAL, supports=True, quality=0.8,
       reproducible=False, peer_reviewed=True, primary=True):
    return EvidenceItem(
        source_id=source, locator="result:1", kind=kind, supports=supports,
        independence_group=group, quality=quality, reproducible=reproducible,
        peer_reviewed=peer_reviewed, primary=primary,
    )


def test_verified_requires_independent_empirical_support_and_reproducibility():
    verifier = TruthVerifier()
    claim = "Treatment A decreases measured recovery time by 12 percent."
    result = verifier.verify_claim(claim, [
        ev("study-a", "lab-a", quality=0.82),
        ev("study-b", "lab-b", kind=EvidenceKind.REPLICATION, quality=0.79, reproducible=True),
    ])
    assert result.state == VerificationState.VERIFIED
    assert result.independent_support == 2
    assert result.empirical_support == 2
    assert result.reproducibility_signal is True
    assert verify_claim_attestation(result) is True


def test_model_consensus_is_not_empirical_evidence():
    verifier = TruthVerifier()
    claim = "System X increases throughput by 40 percent."
    result = verifier.verify_claim(claim, [
        ev("model-observation:a", "model-a", kind=EvidenceKind.MODEL_OBSERVATION, quality=1.0),
        ev("model-observation:b", "model-b", kind=EvidenceKind.MODEL_OBSERVATION, quality=1.0),
        ev("model-observation:c", "model-c", kind=EvidenceKind.MODEL_OBSERVATION, quality=1.0),
    ])
    assert result.state == VerificationState.SPECULATION
    assert result.empirical_support == 0
    assert result.independent_support == 0
    assert "speculation_is_not_evidence" in result.reasons
    assert len(result.rejected_evidence) == 3


def test_same_upstream_source_cannot_fake_independence():
    verifier = TruthVerifier()
    claim = "Measured latency is lower under configuration B."
    result = verifier.verify_claim(claim, [
        ev("article-a", "same-dataset", quality=0.9, reproducible=True),
        ev("article-b", "same-dataset", quality=0.9, reproducible=True),
    ])
    assert result.state == VerificationState.PROVISIONAL
    assert result.independent_support == 1
    assert "insufficient_independent_support" in result.reasons


def test_empirical_contradiction_blocks_verification():
    verifier = TruthVerifier()
    claim = "Method A decreases measured error rate."
    result = verifier.verify_claim(claim, [
        ev("study-a", "lab-a", quality=0.9, reproducible=True),
        ev("study-b", "lab-b", kind=EvidenceKind.REPLICATION, quality=0.9, reproducible=True),
        ev("study-c", "lab-c", supports=False, quality=0.85, reproducible=True),
    ])
    assert result.state == VerificationState.CONTRADICTED
    assert result.independent_contradictions == 1
    assert "contradictory_empirical_evidence" in result.reasons


def test_non_falsifiable_claim_cannot_be_verified():
    verifier = TruthVerifier()
    claim = "This idea is beyond measurement and must be true."
    result = verifier.verify_claim(claim, [
        ev("study-a", "lab-a", quality=0.9, reproducible=True),
        ev("study-b", "lab-b", kind=EvidenceKind.REPLICATION, quality=0.9, reproducible=True),
    ])
    assert result.state != VerificationState.VERIFIED
    assert "claim_not_falsifiable" in result.reasons


def test_attestation_detects_mutation():
    verifier = TruthVerifier()
    result = verifier.verify_claim("Measured output is 10 units.", [
        ev("study-a", "lab-a", quality=0.9, reproducible=True),
        ev("study-b", "lab-b", kind=EvidenceKind.REPLICATION, quality=0.9, reproducible=True),
    ])
    assert verify_claim_attestation(result)
    assert not verify_claim_attestation(replace(result, total_quality=result.total_quality + 0.1))


def test_batch_authoritative_projection_contains_verified_only():
    verifier = TruthVerifier()
    verified = "Measured output is 10 units."
    speculative = "Everyone knows invisible forces make it better."
    batch = verifier.verify_many([verified, speculative], {
        verified: [
            ev("study-a", "lab-a", quality=0.9, reproducible=True),
            ev("study-b", "lab-b", kind=EvidenceKind.REPLICATION, quality=0.9, reproducible=True),
        ],
        speculative: [],
    })
    assert verifier.verified_projection(batch) == (verified,)
    assert [x.claim for x in batch.irrelevant_speculation] == [speculative]
