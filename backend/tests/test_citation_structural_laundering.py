from core.citation_integrity import CitationBinding, CitationIntegrityEngine


def _binding(claim: str, span: str):
    return CitationBinding(
        claim=claim,
        source_id="study-structural",
        locator="doi:study-structural#result",
        binding_method="direct_quote",
        evidence_span=span,
        supports=True,
        provenance_verified=True,
    )


def test_opposite_polarity_cannot_support_same_claim():
    verifier = CitationIntegrityEngine()
    report = verifier.validate(_binding(
        "Algorithm A decreases latency by 10 percent.",
        "Algorithm A does not decrease latency by 10 percent.",
    ))
    assert report.accepted is False
    assert report.laundering_risk == "high"
    assert "evidence_polarity_conflict" in report.reasons


def test_opposite_direction_relation_cannot_support_claim():
    verifier = CitationIntegrityEngine()
    report = verifier.validate(_binding(
        "Algorithm A decreases latency by 10 percent.",
        "Algorithm A increased latency by 10 percent.",
    ))
    assert report.accepted is False
    assert report.laundering_risk == "high"
    assert "evidence_relation_conflict" in report.reasons


def test_unit_mismatch_is_not_laundered_by_matching_number():
    verifier = CitationIntegrityEngine()
    report = verifier.validate(_binding(
        "System A decreases latency by 10 milliseconds.",
        "System A decreased latency by 10 seconds.",
    ))
    assert report.accepted is False
    assert report.laundering_risk == "high"
    assert "claim_unit_not_present_in_evidence_span" in report.reasons


def test_tense_variation_preserves_relation_family():
    verifier = CitationIntegrityEngine()
    report = verifier.validate(_binding(
        "Algorithm A decreases latency by 10 percent.",
        "Algorithm A decreased latency by 10 percent in the preregistered benchmark.",
    ))
    assert report.accepted is True
    assert verifier.verify(report) is True
