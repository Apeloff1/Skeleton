from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.context.semantic_compression import (
    SEMANTIC_COMPRESSION_AUTHORITY_SCOPE,
    SemanticCompressionError,
    SemanticCompressionProposal,
    SemanticCompressionSource,
    qualify_semantic_compression,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust


NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)


def _segment(content: str, *, tenant_id: str = "tenant-a") -> ContextSegment:
    return ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.RETRIEVAL_EVIDENCE,
        source_type="retrieval",
        source_id="source-1",
        content=content,
        trust_level=ContextTrust.UNTRUSTED_EVIDENCE,
        data_class="internal",
        tenant_id=tenant_id,
        purpose="answer",
        priority=10,
        relevance=0.9,
        created_at=NOW,
        provenance=("retrieval:receipt-1",),
        retention_class="request",
    )


def _proposal(candidate: str, facts: tuple[str, ...]) -> SemanticCompressionProposal:
    return SemanticCompressionProposal(
        candidate_content=candidate,
        preserved_facts=facts,
        verifier_id="verifier:semantic-compression",
        verifier_digest="b" * 64,
        verifier_evidence=(
            EvidenceRef(
                source="eval://semantic-compression",
                digest="c" * 64,
                category="semantic-compression-verification",
            ),
        ),
        max_output_tokens=128,
        min_reduction_ratio=0.20,
    )


def test_verified_compression_is_trust_demoted_and_lineage_bound() -> None:
    fact = "The release requires exact-head qualification."
    source = _segment((fact + " Supporting detail. ") * 40)
    receipt = qualify_semantic_compression(
        (SemanticCompressionSource(source, required_facts=(fact,)),),
        _proposal(
            fact + " Remaining detail compressed after independent verification.",
            (fact,),
        ),
    )

    assert receipt.accepted is True
    assert receipt.derived_segment is not None
    assert receipt.derived_segment.trust_level is ContextTrust.DERIVED_UNTRUSTED
    assert receipt.derived_segment.derived_from == (source.segment_id,)
    assert source.content_digest in " ".join(receipt.derived_segment.provenance)
    assert receipt.authority_scope == SEMANTIC_COMPRESSION_AUTHORITY_SCOPE


def test_required_fact_loss_fails_closed() -> None:
    fact = "Never cross tenant boundaries."
    source = _segment((fact + " More context. ") * 30)
    receipt = qualify_semantic_compression(
        (SemanticCompressionSource(source, required_facts=(fact,)),),
        _proposal("A short summary that omits the invariant.", ()),
    )
    assert receipt.accepted is False
    assert "required-fact-not-preserved" in receipt.reasons
    assert receipt.derived_segment is None


def test_cross_tenant_compression_is_rejected() -> None:
    left = _segment("Left evidence. " * 40, tenant_id="tenant-a")
    right = _segment("Right evidence. " * 40, tenant_id="tenant-b")
    receipt = qualify_semantic_compression(
        (SemanticCompressionSource(left), SemanticCompressionSource(right)),
        _proposal("Compressed evidence.", ()),
    )
    assert receipt.accepted is False
    assert "cross-tenant-compression" in receipt.reasons


def test_trusted_control_never_enters_semantic_compressor() -> None:
    trusted = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.SYSTEM_POLICY,
        source_type="platform-policy",
        source_id="policy-1",
        content="System control cannot be summarized by a model.",
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id="tenant-a",
        purpose="answer",
        priority=100,
        relevance=1.0,
        created_at=NOW,
        provenance=("policy:1",),
        retention_class="request",
        mandatory=True,
    )
    with pytest.raises(SemanticCompressionError, match="cannot be semantically compressed"):
        SemanticCompressionSource(trusted)


def test_candidate_must_actually_reduce_context() -> None:
    source = _segment("compact source text")
    receipt = qualify_semantic_compression(
        (SemanticCompressionSource(source),),
        _proposal(
            "compact source text plus more text than the original source",
            (),
        ),
    )
    assert receipt.accepted is False
    assert "not-a-compression" in receipt.reasons
