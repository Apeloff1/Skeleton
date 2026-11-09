from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.evidence_synthesis import (
    EvidenceSignal,
    synthesize_evidence,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_synthesis_requires_independent_domains_for_support():
    signals = (
        EvidenceSignal("a", "attention", d("a"), "family:gqa", 0.95, True),
        EvidenceSignal("b", "kv-cache", d("b"), "family:gqa", 0.90, True),
        EvidenceSignal("c", "topology", d("c"), "family:gqa", 0.85, True),
    )
    report = synthesize_evidence(signals)[0]
    assert report.status == "supported"
    assert report.independent_domains == 3
    assert report.supporting_weight == 0.9
    assert report.contradicting_weight == 0.0


def test_synthesis_surfaces_conflict_instead_of_hiding_it():
    signals = (
        EvidenceSignal("a", "attention", d("a"), "family:gqa", 0.95, True),
        EvidenceSignal("b", "kv-cache", d("b"), "family:gqa", 0.90, True),
        EvidenceSignal("c", "artifact", d("c"), "family:gqa", 0.8, False),
    )
    report = synthesize_evidence(signals)[0]
    assert report.status == "conflicted"
    assert report.net_support < report.supporting_weight
    assert len(report.source_digests) == 3


def test_single_domain_stays_hypothesis_even_with_high_confidence():
    signals = (
        EvidenceSignal("a", "attention", d("a"), "family:mqa", 0.99, True),
        EvidenceSignal("b", "attention", d("b"), "family:mqa", 0.99, True),
    )
    assert synthesize_evidence(signals)[0].status == "hypothesis"
