"""Cross-reference verifier regression tests and adversarial fixtures."""
import pytest
from skeleton.ai.webcrawler.dragon_truth_verifier import (
    Claim, Evidence, EvidenceStance, VerificationStatus,
    VerificationPolicy, verify_claim,
)


CLAIM = Claim("claim-1", "The experiment produced a measurable effect",
              "https://videos.example.org/watch?v=1", 12000)


def evidence(key, family, stance=EvidenceStance.SUPPORTS, *,
             confidence=0.9, provenance="", timestamp=1000, primary=False):
    return Evidence(
        key, CLAIM.claim_id, f"https://sources.example.org/{key}",
        family, stance, "Independent source excerpt",
        timestamp, confidence, primary, provenance,
    )


def test_two_independent_sources_can_corroborate():
    result = verify_claim(CLAIM, (
        evidence("a", "journal"),
        evidence("b", "university", primary=True),
    ), now=1000)
    assert result.status is VerificationStatus.CORROBORATED
    assert result.independent_supporters == 2
    assert result.support_weight > 1.25


def test_reposts_from_same_family_do_not_count_as_independent():
    result = verify_claim(CLAIM, (
        evidence("a", "syndicated-wire"),
        evidence("b", "syndicated-wire"),
        evidence("c", "syndicated-wire"),
    ), now=1000)
    assert result.status is VerificationStatus.INSUFFICIENT
    assert result.independent_supporters == 1


def test_shared_provenance_is_not_double_counted():
    result = verify_claim(CLAIM, (
        evidence("a", "site-a", provenance="shared-wire-1"),
        evidence("b", "site-b", provenance="shared-wire-1"),
    ), now=1000)
    assert result.independent_supporters == 1


def test_opposing_evidence_produces_contested_status():
    result = verify_claim(CLAIM, (
        evidence("a", "journal"),
        evidence("b", "university"),
        evidence("c", "review-board", EvidenceStance.REFUTES),
    ), now=1000)
    assert result.status is VerificationStatus.CONTESTED
    assert result.independent_refuters == 1


def test_independent_refutations_can_refute():
    result = verify_claim(CLAIM, (
        evidence("a", "journal", EvidenceStance.REFUTES),
        evidence("b", "university", EvidenceStance.REFUTES),
    ), now=1000)
    assert result.status is VerificationStatus.REFUTED


def test_low_confidence_and_expired_sources_are_rejected():
    result = verify_claim(CLAIM, (
        evidence("weak", "journal", confidence=0.1),
        evidence("expired", "university", timestamp=0),
    ), now=1000, policy=VerificationPolicy(max_age_days=0.001))
    assert result.status is VerificationStatus.UNVERIFIED
    assert result.rejected_evidence == 2


def test_results_are_order_independent():
    sources = (
        evidence("a", "journal"),
        evidence("b", "university"),
        evidence("c", "university", confidence=0.7),
    )
    assert verify_claim(CLAIM, sources, now=1000) == verify_claim(
        CLAIM, tuple(reversed(sources)), now=1000,
    )


def test_invalid_evidence_budget_fails_closed():
    with pytest.raises(ValueError, match="budget"):
        verify_claim(CLAIM, (evidence("a", "one"), evidence("b", "two")),
                     now=1000, policy=VerificationPolicy(max_evidence=1))


def test_no_evidence_does_not_imply_truth():
    result = verify_claim(CLAIM, (), now=1000)
    assert result.status is VerificationStatus.UNVERIFIED
    assert result.independent_supporters == 0


def test_invalid_source_is_rejected():
    item = Evidence("bad", CLAIM.claim_id, "http://127.0.0.1/private",
                    "untrusted", EvidenceStance.SUPPORTS, "excerpt", 1000, 0.9)
    result = verify_claim(CLAIM, (item,), now=1000)
    assert result.status is VerificationStatus.UNVERIFIED
    assert result.rejected_evidence == 1
