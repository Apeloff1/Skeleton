from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skeleton/jeeves/evidence_response.py"
SPEC = importlib.util.spec_from_file_location("vol072_evidence_response_test", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

JeevesEvidenceAuthority = MODULE.JeevesEvidenceAuthority
JeevesEvidenceError = MODULE.JeevesEvidenceError
JeevesEvidenceKind = MODULE.JeevesEvidenceKind
JeevesEvidenceRecord = MODULE.JeevesEvidenceRecord
JeevesFreshnessPolicy = MODULE.JeevesFreshnessPolicy

NOW = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fact(
    evidence_id: str = "fact.price",
    *,
    observed_at: datetime = NOW - timedelta(seconds=30),
    valid_until: datetime | None = None,
) -> JeevesEvidenceRecord:
    return JeevesEvidenceRecord(
        evidence_id=evidence_id,
        kind=JeevesEvidenceKind.MARKET_FACT,
        summary="Instrument X last trade was 101.25.",
        content_digest=digest(evidence_id),
        source_id="market-feed-primary",
        source_uri="https://example.invalid/market/X",
        observed_at=observed_at.isoformat(),
        valid_until=valid_until.isoformat() if valid_until else None,
    )


def analysis(
    evidence_id: str = "analysis.momentum",
    *,
    depends_on: tuple[str, ...] = ("fact.price",),
) -> JeevesEvidenceRecord:
    return JeevesEvidenceRecord(
        evidence_id=evidence_id,
        kind=JeevesEvidenceKind.ANALYSIS,
        summary="Observed movement is positive over the bounded window.",
        content_digest=digest(evidence_id),
        depends_on=depends_on,
        confidence=0.75,
    )


def prediction(
    evidence_id: str = "prediction.next",
    *,
    depends_on: tuple[str, ...] = ("analysis.momentum",),
) -> JeevesEvidenceRecord:
    return JeevesEvidenceRecord(
        evidence_id=evidence_id,
        kind=JeevesEvidenceKind.PREDICTION,
        summary="Conditional forecast: positive movement may persist.",
        content_digest=digest(evidence_id),
        depends_on=depends_on,
        confidence=0.61,
        prediction_horizon_seconds=900,
    )


def authority(max_age: int = 120) -> JeevesEvidenceAuthority:
    return JeevesEvidenceAuthority(JeevesFreshnessPolicy(max_age_seconds=max_age))


def test_response_preserves_fact_analysis_prediction_separation_and_receipt() -> None:
    response = authority().assemble([prediction(), fact(), analysis()], now=NOW)
    assert [item.evidence_id for item in response.facts] == ["fact.price"]
    assert [item.evidence_id for item in response.analyses] == ["analysis.momentum"]
    assert [item.evidence_id for item in response.predictions] == ["prediction.next"]
    assert len(response.receipt_digest) == 64
    assert response.to_wire()["facts"][0]["source_id"] == "market-feed-primary"
    authority().verify(response)


def test_receipt_is_deterministic_across_input_order() -> None:
    first = authority().assemble([fact(), analysis(), prediction()], now=NOW)
    second = authority().assemble([prediction(), analysis(), fact()], now=NOW)
    assert first.receipt_digest == second.receipt_digest
    assert first.to_wire() == second.to_wire()


def test_stale_market_fact_fails_closed() -> None:
    with pytest.raises(JeevesEvidenceError, match="stale"):
        authority().assemble([fact(observed_at=NOW - timedelta(seconds=121))], now=NOW)


def test_future_market_fact_beyond_clock_skew_fails_closed() -> None:
    with pytest.raises(JeevesEvidenceError, match="future clock skew"):
        authority().assemble([fact(observed_at=NOW + timedelta(seconds=6))], now=NOW)


def test_expired_market_fact_fails_closed() -> None:
    with pytest.raises(JeevesEvidenceError, match="expired"):
        authority().assemble([fact(valid_until=NOW - timedelta(seconds=1))], now=NOW)


def test_market_fact_requires_source_timestamp_and_digest_provenance() -> None:
    with pytest.raises(JeevesEvidenceError, match="source_id"):
        JeevesEvidenceRecord(
            evidence_id="fact.bad",
            kind=JeevesEvidenceKind.MARKET_FACT,
            summary="unproven fact",
            content_digest=digest("bad"),
            source_uri="https://example.invalid/data",
            observed_at=NOW.isoformat(),
        )


def test_analysis_cannot_masquerade_as_sourced_fact() -> None:
    with pytest.raises(JeevesEvidenceError, match="fact source fields"):
        JeevesEvidenceRecord(
            evidence_id="analysis.bad",
            kind=JeevesEvidenceKind.ANALYSIS,
            summary="analysis",
            content_digest=digest("analysis.bad"),
            depends_on=("fact.price",),
            source_id="pretend-source",
        )


def test_prediction_requires_confidence_and_horizon() -> None:
    with pytest.raises(JeevesEvidenceError, match="confidence"):
        JeevesEvidenceRecord(
            evidence_id="prediction.bad",
            kind=JeevesEvidenceKind.PREDICTION,
            summary="prediction",
            content_digest=digest("prediction.bad"),
            depends_on=("fact.price",),
            prediction_horizon_seconds=60,
        )


def test_unknown_dependency_fails_closed() -> None:
    with pytest.raises(JeevesEvidenceError, match="unknown dependency"):
        authority().assemble([fact(), analysis(depends_on=("fact.missing",))], now=NOW)


def test_duplicate_evidence_identity_fails_closed() -> None:
    with pytest.raises(JeevesEvidenceError, match="duplicate evidence identity"):
        authority().assemble([fact(), fact()], now=NOW)


def test_dependency_cycle_fails_closed() -> None:
    left = analysis("analysis.left", depends_on=("analysis.right",))
    right = analysis("analysis.right", depends_on=("analysis.left",))
    with pytest.raises(JeevesEvidenceError, match="cycle"):
        authority().assemble([fact(), left, right], now=NOW)


def test_analysis_cannot_treat_prediction_as_factual_support() -> None:
    pred = prediction("prediction.direct", depends_on=("fact.price",))
    derived = analysis("analysis.from-prediction", depends_on=("prediction.direct",))
    with pytest.raises(JeevesEvidenceError, match="analysis cannot use prediction"):
        authority().assemble([fact(), pred, derived], now=NOW)


def test_noncanonical_digest_fails_at_record_construction() -> None:
    with pytest.raises(JeevesEvidenceError, match="lowercase canonical sha256"):
        JeevesEvidenceRecord(
            evidence_id="fact.bad-digest",
            kind=JeevesEvidenceKind.MARKET_FACT,
            summary="fact",
            content_digest="A" * 64,
            source_id="market-feed-primary",
            source_uri="urn:market:primary",
            observed_at=NOW.isoformat(),
        )


def test_receipt_tampering_is_detected() -> None:
    response = authority().assemble([fact(), analysis(), prediction()], now=NOW)
    forged = replace(response, receipt_digest="0" * 64)
    with pytest.raises(JeevesEvidenceError, match="receipt"):
        authority().verify(forged)


def test_canonical_and_governed_ai_authority_are_byte_identical() -> None:
    canonical = ROOT / "skeleton/jeeves/evidence_response.py"
    mirror = ROOT / "skeleton/ai/agents/jeeves/evidence_response.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_custody_manifest_exactly_classifies_all_jeeves_lineages() -> None:
    custody = json.loads((ROOT / "machine/jeeves_custody.json").read_text(encoding="utf-8"))
    entries = {entry["mapping_id"]: entry for entry in custody["entries"]}
    assert len(entries) == 7
    assert sum(entry["runtime_authority"] is True for entry in entries.values()) == 1
    assert entries["AIFT-JEEVES"]["custody"] == "canonical_authority"
    assert entries["AIFT-V2B-GAMEFORGE-JEEVES"]["custody"] == "research_quarantine"
    assert all(
        entry["custody"] == "compatibility_only"
        for mapping_id, entry in entries.items()
        if "BACKEND-CORE" in mapping_id
    )


def test_response_group_tampering_is_detected() -> None:
    response = authority().assemble([fact(), analysis(), prediction()], now=NOW)
    forged = replace(
        response,
        facts=response.facts + response.analyses,
        analyses=(),
    )
    with pytest.raises(JeevesEvidenceError, match="canonical grouping"):
        authority().verify(forged)
