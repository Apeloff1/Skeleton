from __future__ import annotations

from skeleton.contracts.canonical import (
    CanonicalEnvelope,
    EvidenceRef,
    Identity,
    evidence_ref_identity,
)
from skeleton.contracts.evidence_ingestion import (
    EvidenceDisposition,
    ingest_execution_evidence,
)


IDENTITY = Identity(
    repository="Apeloff1/Skeleton",
    commit_sha="a" * 40,
    run_id="run-1",
    run_attempt="1",
)


def _envelope(*evidence: EvidenceRef, kind: str = "execution_result") -> CanonicalEnvelope:
    return CanonicalEnvelope(
        schema_version=1,
        kind=kind,
        identity=IDENTITY,
        evidence=tuple(evidence),
        constraints=(),
        payload={"status": "ok"},
    )


def test_canonical_evidence_ref_has_stable_content_identity() -> None:
    left = EvidenceRef(source="pytest:test-a", digest="1" * 64, category="test")
    right = EvidenceRef(source="pytest:test-a", digest="1" * 64, category="test")

    assert left.identity == right.identity
    assert left.identity == evidence_ref_identity(left)
    assert len(left.identity) == 64


def test_ingestion_accepts_real_canonical_evidence_refs() -> None:
    ref = EvidenceRef(source="pytest:test-a", digest="1" * 64, category="test")

    decision = ingest_execution_evidence(_envelope(ref))

    assert decision.disposition is EvidenceDisposition.STABLE
    assert decision.reason == "validated execution evidence"
    assert decision.evidence_ids == (ref.identity,)


def test_ingestion_is_order_independent_and_deduplicates_refs() -> None:
    first = EvidenceRef(source="pytest:a", digest="1" * 64, category="test")
    second = EvidenceRef(source="pytest:b", digest="2" * 64, category="test")

    left = ingest_execution_evidence(_envelope(first, second, first))
    right = ingest_execution_evidence(_envelope(second, first))

    assert left.disposition is EvidenceDisposition.STABLE
    assert left.evidence_ids == right.evidence_ids
    assert len(left.evidence_ids) == 2


def test_ingestion_keeps_incomplete_evidence_temporary() -> None:
    incomplete = EvidenceRef(source="", digest="1" * 64, category="test")

    decision = ingest_execution_evidence(_envelope(incomplete))

    assert decision.disposition is EvidenceDisposition.TEMPORARY
    assert decision.evidence_ids == ()


def test_ingestion_rejects_wrong_envelope_kind() -> None:
    ref = EvidenceRef(source="pytest:test-a", digest="1" * 64, category="test")

    decision = ingest_execution_evidence(_envelope(ref, kind="proposal"))

    assert decision.disposition is EvidenceDisposition.REJECTED
    assert decision.evidence_ids == ()
