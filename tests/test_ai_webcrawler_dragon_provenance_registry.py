"""Regression tests for attested cross-reference independence."""
import pytest

from skeleton.ai.webcrawler.dragon_provenance_registry import (
    ProvenanceRegistry, SourceAttestation, ProvenancePolicy,
)
from skeleton.ai.webcrawler.dragon_truth_verifier import (
    Claim, Evidence, EvidenceStance, VerificationStatus,
)


CLAIM = Claim("fact-1", "A measurable event occurred",
              "https://videos.example.org/watch?v=1")


def attested(host, owner, syndication=""):
    return SourceAttestation(
        host, owner, syndication, verified_by="curator-1",
        evidence_reference=f"registry:{host}",
    )


def source(key, host, family="untrusted"):
    return Evidence(
        key, "fact-1", f"https://{host}/article/{key}",
        family, EvidenceStance.SUPPORTS, "Relevant independent excerpt",
        1000, 0.9,
    )


def test_shared_owner_is_not_independent():
    registry = ProvenanceRegistry((
        attested("news-a.example.org", "parent-company"),
        attested("news-b.example.org", "parent-company"),
    ))
    review = registry.verify(CLAIM, (
        source("one", "news-a.example.org"),
        source("two", "news-b.example.org"),
    ), now=1000)
    assert review.result.status is VerificationStatus.INSUFFICIENT
    assert review.result.independent_supporters == 1


def test_distinct_attested_owners_corroborate():
    registry = ProvenanceRegistry((
        attested("news-a.example.org", "company-a"),
        attested("news-b.example.org", "company-b"),
    ))
    review = registry.verify(CLAIM, (
        source("one", "news-a.example.org"),
        source("two", "news-b.example.org"),
    ), now=1000)
    assert review.result.status is VerificationStatus.CORROBORATED
    assert review.result.independent_supporters == 2


def test_shared_syndication_overrides_distinct_owners():
    registry = ProvenanceRegistry((
        attested("news-a.example.org", "company-a", "wire-x"),
        attested("news-b.example.org", "company-b", "wire-x"),
    ))
    review = registry.verify(CLAIM, (
        source("one", "news-a.example.org"),
        source("two", "news-b.example.org"),
    ), now=1000)
    assert review.result.independent_supporters == 1


def test_unknown_publishers_fail_closed():
    registry = ProvenanceRegistry((
        attested("news-a.example.org", "company-a"),
    ))
    review = registry.verify(CLAIM, (
        source("one", "news-a.example.org"),
        source("two", "unknown.example.org"),
    ), now=1000)
    assert review.rejected_sources == 1
    assert review.result.status is VerificationStatus.INSUFFICIENT


def test_duplicate_attestation_conflicts_are_rejected():
    with pytest.raises(ValueError, match="conflicting"):
        ProvenanceRegistry((
            attested("news-a.example.org", "company-a"),
            attested("news-a.example.org", "company-b"),
        ))


def test_registry_fingerprint_is_order_independent():
    a = attested("news-a.example.org", "company-a")
    b = attested("news-b.example.org", "company-b")
    assert ProvenanceRegistry((a, b)).fingerprint == ProvenanceRegistry(
        (b, a)
    ).fingerprint


def test_unverified_attestation_is_rejected():
    with pytest.raises(ValueError, match="unverified"):
        ProvenanceRegistry((
            SourceAttestation("news-a.example.org", "company-a"),
        ))


def test_unknown_publishers_do_not_gain_independence_when_allowed():
    registry = ProvenanceRegistry((), policy=ProvenancePolicy(
        require_attestation=False,
    ))
    review = registry.verify(CLAIM, (
        source("one", "unknown-a.example.org"),
        source("two", "unknown-b.example.org"),
    ), now=1000)
    assert review.result.independent_supporters == 1
