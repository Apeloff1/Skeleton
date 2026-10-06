from __future__ import annotations

import hashlib

import pytest

from core.chat_evidence import (
    ChatEvidenceError,
    ChatEvidenceGate,
    ClaimEvidence,
    EvidencePolicy,
    EvidenceRequirement,
    SourceClass,
)


CLAIM = "System A reduces measured latency by 10 percent."
NOW = 10_000.0


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _candidate(
    source_id: str = "source-a",
    *,
    supports: bool = True,
    source_class: SourceClass = SourceClass.AUTHORITATIVE,
    quality: float = 0.9,
    group: str = "group-a",
    observed_at: float | None = NOW - 60,
    span: str | None = None,
    provenance_verified: bool = True,
) -> ClaimEvidence:
    evidence_span = span or (
        "Measurement record: System A reduces measured latency by "
        "10 percent."
    )
    return ClaimEvidence(
        source_id=source_id,
        locator="record:" + source_id + "#result",
        evidence_span=evidence_span,
        binding_method="measurement_record",
        supports=supports,
        provenance_verified=provenance_verified,
        source_content_sha256=_digest(evidence_span),
        source_class=source_class,
        quality=quality,
        independence_group=group,
        observed_at=observed_at,
    )


def test_evidence_supported_claim_accepts_integrity_bound_source() -> None:
    decision = ChatEvidenceGate().evaluate(
        CLAIM,
        (_candidate(),),
        policy=EvidencePolicy.for_requirement(
            EvidenceRequirement.EVIDENCE_SUPPORTED
        ),
        now=NOW,
    )
    assert decision.accepted is True
    assert decision.reasons == ()
    assert len(decision.citations) == 1
    assert len(decision.citations[0].citation_attestation_sha256) == 64
    assert len(decision.digest) == 64


def test_unverified_provenance_is_rejected_before_counting_support() -> None:
    decision = ChatEvidenceGate().evaluate(
        CLAIM,
        (_candidate(provenance_verified=False),),
        policy=EvidencePolicy.for_requirement(
            EvidenceRequirement.EVIDENCE_SUPPORTED
        ),
        now=NOW,
    )
    assert decision.accepted is False
    assert "insufficient-supporting-sources" in decision.reasons
    source, reasons = decision.rejected_sources[0]
    assert source == "source-a"
    assert "citation:source_provenance_unverified" in reasons


def test_claim_quantity_must_exist_in_evidence_span() -> None:
    decision = ChatEvidenceGate().evaluate(
        CLAIM,
        (
            _candidate(
                span="Measurement record: System A reduces measured latency.",
            ),
        ),
        policy=EvidencePolicy.for_requirement(
            EvidenceRequirement.EVIDENCE_SUPPORTED
        ),
        now=NOW,
    )
    assert decision.accepted is False
    assert any(
        "claim_quantity_not_present" in reason
        for _source, reasons in decision.rejected_sources
        for reason in reasons
    )


def test_freshness_required_rejects_missing_stale_and_future_metadata() -> None:
    policy = EvidencePolicy(
        EvidenceRequirement.FRESHNESS_REQUIRED,
        min_supporting_sources=1,
        min_independence_groups=1,
        min_quality=0.4,
        max_age_s=100,
    )
    missing = ChatEvidenceGate().evaluate(
        CLAIM,
        (_candidate(observed_at=None),),
        policy=policy,
        now=NOW,
    )
    assert missing.accepted is False
    assert "freshness-metadata-missing" in missing.rejected_sources[0][1]

    stale = ChatEvidenceGate().evaluate(
        CLAIM,
        (_candidate(observed_at=NOW - 101),),
        policy=policy,
        now=NOW,
    )
    assert stale.accepted is False
    assert "source-stale" in stale.rejected_sources[0][1]

    future = ChatEvidenceGate().evaluate(
        CLAIM,
        (_candidate(observed_at=NOW + 1),),
        policy=policy,
        now=NOW,
    )
    assert future.accepted is False
    assert "freshness-timestamp-in-future" in future.rejected_sources[0][1]


def test_authoritative_requirement_rejects_secondary_source() -> None:
    policy = EvidencePolicy.for_requirement(
        EvidenceRequirement.AUTHORITATIVE_SOURCE_REQUIRED
    )
    rejected = ChatEvidenceGate().evaluate(
        CLAIM,
        (_candidate(source_class=SourceClass.SECONDARY),),
        policy=policy,
        now=NOW,
    )
    assert rejected.accepted is False
    assert "source-class-not-allowed" in rejected.rejected_sources[0][1]

    accepted = ChatEvidenceGate().evaluate(
        CLAIM,
        (_candidate(source_class=SourceClass.PRIMARY),),
        policy=policy,
        now=NOW,
    )
    assert accepted.accepted is True


def test_high_assurance_requires_independent_support() -> None:
    policy = EvidencePolicy.for_requirement(
        EvidenceRequirement.HIGH_ASSURANCE
    )
    same_group = ChatEvidenceGate().evaluate(
        CLAIM,
        (
            _candidate("a", group="same"),
            _candidate("b", group="same"),
        ),
        policy=policy,
        now=NOW,
    )
    assert same_group.accepted is False
    assert "insufficient-independent-evidence" in same_group.reasons

    independent = ChatEvidenceGate().evaluate(
        CLAIM,
        (
            _candidate("a", group="group-a"),
            _candidate("b", group="group-b"),
        ),
        policy=policy,
        now=NOW,
    )
    assert independent.accepted is True


def test_valid_contradicting_evidence_blocks_release_by_default() -> None:
    support = _candidate("support", group="group-a")
    contradict = _candidate(
        "contradict",
        supports=False,
        group="group-b",
        span=(
            "Measurement record: System A does not reduce measured "
            "latency by 10 percent."
        ),
    )
    decision = ChatEvidenceGate().evaluate(
        CLAIM,
        (support, contradict),
        policy=EvidencePolicy.for_requirement(
            EvidenceRequirement.EVIDENCE_SUPPORTED
        ),
        now=NOW,
    )
    assert decision.accepted is False
    assert "accepted-contradicting-evidence-present" in decision.reasons
    assert {item.source_id for item in decision.citations} == {
        "support",
        "contradict",
    }


def test_synthesis_only_can_release_without_external_evidence() -> None:
    decision = ChatEvidenceGate().evaluate(
        "Summarize the supplied text.",
        (),
        policy=EvidencePolicy.for_requirement(
            EvidenceRequirement.SYNTHESIS_ONLY
        ),
        now=NOW,
    )
    assert decision.accepted is True
    assert decision.citations == ()


def test_decision_digest_is_deterministic_for_same_evidence_and_time() -> None:
    gate = ChatEvidenceGate()
    policy = EvidencePolicy.for_requirement(
        EvidenceRequirement.EVIDENCE_SUPPORTED
    )
    first = gate.evaluate(
        CLAIM,
        (_candidate("b"), _candidate("a")),
        policy=policy,
        now=NOW,
    )
    second = gate.evaluate(
        CLAIM,
        (_candidate("a"), _candidate("b")),
        policy=policy,
        now=NOW,
    )
    assert first.digest == second.digest
    assert first == second


def test_policy_and_candidate_numeric_inputs_fail_closed() -> None:
    with pytest.raises(ChatEvidenceError, match="freshness-required"):
        EvidencePolicy(
            EvidenceRequirement.FRESHNESS_REQUIRED,
            max_age_s=None,
        )
    with pytest.raises(ChatEvidenceError, match="within"):
        _candidate(quality=float("nan"))
    with pytest.raises(ChatEvidenceError, match="authoritative-source"):
        EvidencePolicy(
            EvidenceRequirement.HIGH_ASSURANCE,
            max_age_s=60,
            allowed_source_classes=frozenset(
                {SourceClass.AUTHORITATIVE, SourceClass.SECONDARY}
            ),
        )
