import asyncio

import pytest

from core.calibration_ledger import CalibrationIntegrityError, CalibrationLedger
from core.citation_integrity import CitationBinding, CitationIntegrityEngine
from core.claim_identity import ClaimIdentityEngine
from core.curiosity_engine import Inquiry
from core.curiosity_research_pipeline import EnsembleCuriosityResearcher


def _inquiry() -> Inquiry:
    return Inquiry(
        id="i1",
        subject="latency",
        questions=("Does A reduce latency?",),
        context_record_ids=(),
        keywords=("latency",),
        score=1.0,
        reason="test",
    )


def test_claim_identity_normalizes_format_but_preserves_truth_material_differences():
    engine = ClaimIdentityEngine()
    equivalent = engine.compare(
        "Algorithm A decreases latency by 10 percent.",
        "Algorithm A decreases latency by 10%.",
    )
    assert equivalent.identity_equal is True
    assert equivalent.disposition == "same_identity"
    assert engine.verify(equivalent) is True

    negated = engine.compare(
        "Algorithm A decreases latency by 10 percent.",
        "Algorithm A does not decrease latency by 10 percent.",
    )
    assert negated.identity_equal is False
    assert "polarity_differs" in negated.reasons

    changed_quantity = engine.compare(
        "Algorithm A decreases latency by 10 percent.",
        "Algorithm A decreases latency by 12 percent.",
    )
    assert changed_quantity.identity_equal is False
    assert "quantities_differ" in changed_quantity.reasons


def test_citation_integrity_rejects_topic_adjacent_and_numeric_laundering():
    validator = CitationIntegrityEngine()
    valid = validator.validate(CitationBinding(
        claim="Algorithm A decreases latency by 10 percent.",
        source_id="study-a",
        locator="doi:study-a#result-2",
        binding_method="direct_quote",
        evidence_span="Algorithm A decreases latency by 10 percent compared with control.",
        supports=True,
        provenance_verified=True,
    ))
    assert valid.accepted is True
    assert validator.verify(valid) is True

    adjacent = validator.validate(CitationBinding(
        claim="Algorithm A decreases latency by 10 percent.",
        source_id="study-a",
        locator="doi:study-a#introduction",
        binding_method="direct_quote",
        evidence_span="Distributed systems frequently experience latency under load.",
        supports=True,
        provenance_verified=True,
    ))
    assert adjacent.accepted is False
    assert "insufficient_claim_anchor_overlap" in adjacent.reasons

    numeric_laundering = validator.validate(CitationBinding(
        claim="Algorithm A decreases latency by 10 percent.",
        source_id="study-a",
        locator="doi:study-a#table-4",
        binding_method="table",
        evidence_span="Algorithm A decreased latency by 3 percent.",
        supports=True,
        provenance_verified=True,
        mapping_rationale="Table 4 directly reports the latency delta for Algorithm A.",
    ))
    assert numeric_laundering.accepted is False
    assert "claim_quantity_not_present_in_evidence_span" in numeric_laundering.reasons
    assert numeric_laundering.laundering_risk == "high"


def test_calibration_is_measurement_not_truth_and_resolution_is_immutable(tmp_path):
    ledger = CalibrationLedger(tmp_path)
    forecast = ledger.forecast(
        claim="Measured output exceeds 10 units.",
        probability=0.8,
        forecaster="model-a",
        forecast_id="forecast-1",
    )
    assert ledger.metrics()["calibration_available"] is False
    resolved = ledger.resolve(
        forecast.id,
        outcome=True,
        verification_attestation_sha256="a" * 64,
    )
    assert resolved.outcome is True
    metrics = ledger.metrics()
    assert metrics["resolved"] == 1
    assert metrics["brier_score"] == 0.04

    assert ledger.resolve(forecast.id, outcome=True, verification_attestation_sha256="a" * 64).outcome is True
    with pytest.raises(CalibrationIntegrityError):
        ledger.resolve(forecast.id, outcome=False, verification_attestation_sha256="b" * 64)


def test_research_pipeline_refuses_legacy_claim_labels_without_binding():
    claim = "Algorithm A decreases latency by 10 percent."

    async def completion(model, prompt, system):
        return {"summary": "candidate", "claims": [claim], "questions": [], "contradictions": [], "tags": []}

    async def source_search(inquiry, questions):
        return [{
            "source": "study-a",
            "locator": "doi:study-a",
            "excerpt": "Algorithm A decreases latency by 10 percent.",
            "kind": "primary_empirical",
            "independence_group": "lab-a",
            "quality": 1.0,
            "supports_claims": [claim],
            "provenance_verified": True,
        }]

    researcher = EnsembleCuriosityResearcher(completion, models=("m1",), source_search=source_search)
    finding = asyncio.run(researcher(_inquiry(), {}))
    assert finding["claim_bound_evidence_count"] == 0
    assert finding["citation_integrity"]["rejected"] == 1
    assert finding["citation_integrity"]["reports"][0]["reasons"] == ["legacy_claim_label_without_inspectable_binding"]


def test_research_pipeline_accepts_inspectable_binding_and_deduplicates_identity_variants():
    canonical = "Algorithm A decreases latency by 10 percent."
    variant = "Algorithm A decreases latency by 10%."

    async def completion(model, prompt, system):
        claim = canonical if model == "m1" else variant
        return {"summary": "candidate", "claims": [claim], "questions": [], "contradictions": [], "tags": []}

    async def source_search(inquiry, questions):
        return [{
            "source": "study-a",
            "locator": "doi:study-a#result",
            "excerpt": "Algorithm A decreases latency by 10 percent compared with control.",
            "kind": "primary_empirical",
            "independence_group": "lab-a",
            "quality": 1.0,
            "provenance_verified": True,
            "claim_bindings": [{
                "claim": variant,
                "supports": True,
                "binding_method": "direct_quote",
                "evidence_span": "Algorithm A decreases latency by 10 percent compared with control.",
            }],
        }]

    researcher = EnsembleCuriosityResearcher(completion, models=("m1", "m2"), source_search=source_search)
    finding = asyncio.run(researcher(_inquiry(), {}))
    assert finding["claims"] == [canonical]
    assert finding["semantic_variants"][canonical] == sorted([canonical, variant])
    assert finding["claim_bound_evidence_count"] == 1
    assert finding["citation_integrity"]["accepted"] == 1
