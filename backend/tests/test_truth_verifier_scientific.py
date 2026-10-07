from core.epistemic_gate import EpistemicGate
from core.truth_verifier import (
    EvidenceItem,
    EvidenceKind,
    TruthVerifier,
    VerificationState,
    effective_evidence_quality,
    verify_claim_attestation,
)


def _study(
    source: str,
    group: str,
    *,
    kind: EvidenceKind = EvidenceKind.PRIMARY_EMPIRICAL,
    supports: bool = True,
    provenance: bool = True,
    replication: bool = False,
    quality: float = 1.0,
) -> EvidenceItem:
    return EvidenceItem(
        source_id=source,
        locator=f"doi:{source}",
        kind=EvidenceKind.REPLICATION if replication else kind,
        supports=supports,
        independence_group=group,
        quality=quality,
        reproducible=replication,
        peer_reviewed=True,
        primary=True,
        provenance_verified=provenance,
        preregistered=True,
        data_available=True,
        code_available=True,
        sample_size=300,
        uncertainty_reported=True,
    )


def test_caller_cannot_self_award_evidence_quality():
    weak = EvidenceItem(
        source_id="weak-study",
        locator="paper:1",
        kind=EvidenceKind.PRIMARY_EMPIRICAL,
        supports=True,
        independence_group="lab-a",
        quality=1.0,
        provenance_verified=True,
    )
    assert effective_evidence_quality(weak) < 0.5


def test_unverified_provenance_is_not_empirical_support():
    verifier = TruthVerifier()
    claim = "Intervention X decreases measured latency by 10 percent."
    result = verifier.verify_claim(
        claim,
        [
            _study("a", "lab-a", provenance=False),
            _study("b", "lab-b", replication=True, provenance=False),
        ],
        falsifiable=True,
    )
    assert result.state == VerificationState.SPECULATION
    assert result.provenance_verified_support == 0
    assert "no_verified_provenance" in result.reasons
    assert verify_claim_attestation(result) is True


def test_replication_from_same_independence_group_does_not_verify():
    verifier = TruthVerifier()
    claim = "Algorithm A decreases measured runtime by 15 percent."
    result = verifier.verify_claim(
        claim,
        [
            _study("original", "lab-a"),
            _study("repeat", "lab-a", replication=True),
        ],
        falsifiable=True,
    )
    assert result.state != VerificationState.VERIFIED
    assert result.independent_support == 1
    assert result.independent_replication is False
    assert "insufficient_independent_support" in result.reasons
    assert "no_independent_replication" in result.reasons


def test_independent_high_quality_replication_promotes_verified_claim():
    verifier = TruthVerifier()
    claim = "Algorithm A decreases measured runtime by 15 percent."
    result = verifier.verify_claim(
        claim,
        [
            _study("original", "lab-a"),
            _study("replication", "lab-b", replication=True),
        ],
        falsifiable=True,
    )
    assert result.state == VerificationState.VERIFIED
    assert result.independent_support == 2
    assert result.independent_replication is True
    assert result.provenance_verified_support == 2
    assert result.mean_quality >= 0.8
    assert result.reasons == ()


def test_model_consensus_remains_irrelevant_speculation():
    verifier = TruthVerifier()
    claim = "Device Q produces net-positive measured energy."
    observations = [
        EvidenceItem(
            source_id=f"model-{index}",
            locator="panel",
            kind=EvidenceKind.MODEL_OBSERVATION,
            supports=True,
            independence_group=f"model-{index}",
            quality=1.0,
            provenance_verified=True,
        )
        for index in range(5)
    ]
    result = verifier.verify_claim(claim, observations, falsifiable=True)
    assert result.state == VerificationState.SPECULATION
    assert result.empirical_support == 0
    assert result.independent_support == 0
    assert "speculation_is_not_evidence" in result.reasons


def test_epistemic_gate_propagates_methodology_and_replication_fields():
    claim = "Treatment B decreases measured recovery time by 8 percent."
    gate = EpistemicGate()
    decision = gate.evaluate({
        "claims": [claim],
        "falsifiable": {claim: True},
        "claim_evidence": {claim: [
            {
                "source_id": "study-a",
                "locator": "doi:a",
                "kind": "primary_empirical",
                "supports": True,
                "independence_group": "lab-a",
                "quality": 1.0,
                "provenance_verified": True,
                "peer_reviewed": True,
                "primary": True,
                "preregistered": True,
                "data_available": True,
                "code_available": True,
                "sample_size": 180,
                "uncertainty_reported": True,
                "citation_binding": {
                    "binding_method": "direct_quote",
                    "evidence_span": claim,
                },
            },
            {
                "source_id": "study-b",
                "locator": "doi:b",
                "kind": "replication",
                "supports": True,
                "independence_group": "lab-b",
                "quality": 1.0,
                "provenance_verified": True,
                "reproducible": True,
                "peer_reviewed": True,
                "primary": True,
                "preregistered": True,
                "data_available": True,
                "code_available": True,
                "sample_size": 220,
                "uncertainty_reported": True,
                "citation_binding": {
                    "binding_method": "direct_quote",
                    "evidence_span": claim,
                },
            },
        ]},
    })
    assert decision.verified_claims == (claim,)
    row = decision.verification[claim]
    assert row["provenance_verified_support"] == 2
    assert row["independent_replication"] is True
    assert row["state"] == "verified"
