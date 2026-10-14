"""Verifier-gated semantic context compression for VOL-009.

Compressed output is always DERIVED_UNTRUSTED and remains bound to every source
segment/content digest, verifier receipt, tenant, purpose, data class and
retention class. This module validates candidates; it never lets a summarizer
inherit or manufacture control authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.canonical import EvidenceRef, canonical_json_bytes
from skeleton.contracts.context import (
    ContextKind,
    ContextSegment,
    ContextTrust,
    estimate_tokens,
)


SEMANTIC_COMPRESSION_VERSION = "semantic-compression-v1"
SEMANTIC_COMPRESSION_AUTHORITY_SCOPE = "context-evidence-only"
_MAX_SOURCES = 128
_MAX_FACTS = 512
_CONVERSATION_KINDS = frozenset(
    {
        ContextKind.USER_MESSAGE,
        ContextKind.ASSISTANT_MESSAGE,
        ContextKind.CONVERSATION_SUMMARY,
    }
)


class SemanticCompressionError(ValueError):
    """A semantic compression candidate cannot be admitted safely."""


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise SemanticCompressionError(f"{field} must be normalized non-empty text")
    if len(value) > maximum:
        raise SemanticCompressionError(f"{field} exceeds length limit")
    return value


def _sha(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise SemanticCompressionError(f"{field} must be lowercase sha256")
    return value


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise SemanticCompressionError("verifier evidence must contain EvidenceRef")
    indexed: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise SemanticCompressionError("verifier evidence must contain EvidenceRef")
        _text(item.source, "evidence.source", maximum=2048)
        _sha(item.digest, "evidence.digest")
        _text(item.category, "evidence.category", maximum=128)
        indexed[(item.source, item.digest, item.category)] = item
    if not indexed:
        raise SemanticCompressionError("verifier evidence must be non-empty")
    return tuple(indexed[key] for key in sorted(indexed))


def _digest(payload: object) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class SemanticCompressionSource:
    segment: ContextSegment
    required_facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.segment, ContextSegment):
            raise TypeError("segment must be ContextSegment")
        if (
            self.segment.trust_level is ContextTrust.TRUSTED_CONTROL
            or self.segment.mandatory
        ):
            raise SemanticCompressionError(
                "trusted control and mandatory context cannot be semantically compressed"
            )
        if self.segment.content is None:
            raise SemanticCompressionError(
                "semantic compression requires materialized source content"
            )
        if isinstance(self.required_facts, (str, bytes)):
            raise SemanticCompressionError("required_facts must be a tuple")
        normalized: list[str] = []
        for fact in self.required_facts:
            fact = _text(fact, "required_fact", maximum=2048)
            if fact not in self.segment.content:
                raise SemanticCompressionError(
                    "required fact is not present in its source segment"
                )
            normalized.append(fact)
        if len(normalized) > _MAX_FACTS:
            raise SemanticCompressionError("required_facts exceeds item limit")
        object.__setattr__(self, "required_facts", tuple(sorted(set(normalized))))


@dataclass(frozen=True, slots=True)
class SemanticCompressionProposal:
    candidate_content: str
    preserved_facts: tuple[str, ...]
    verifier_id: str
    verifier_digest: str
    verifier_evidence: tuple[EvidenceRef, ...]
    max_output_tokens: int
    min_reduction_ratio: float = 0.20
    compression_version: str = SEMANTIC_COMPRESSION_VERSION
    independent: bool = True
    authority_scope: str = SEMANTIC_COMPRESSION_AUTHORITY_SCOPE

    def __post_init__(self) -> None:
        _text(self.candidate_content, "candidate_content", maximum=500_000)
        if isinstance(self.preserved_facts, (str, bytes)):
            raise SemanticCompressionError("preserved_facts must be a tuple")
        facts = tuple(
            sorted(
                {
                    _text(item, "preserved_fact", maximum=2048)
                    for item in self.preserved_facts
                }
            )
        )
        if len(facts) > _MAX_FACTS:
            raise SemanticCompressionError("preserved_facts exceeds item limit")
        object.__setattr__(self, "preserved_facts", facts)
        object.__setattr__(self, "verifier_id", _text(self.verifier_id, "verifier_id"))
        object.__setattr__(
            self,
            "verifier_digest",
            _sha(self.verifier_digest, "verifier_digest"),
        )
        object.__setattr__(
            self,
            "verifier_evidence",
            _evidence(self.verifier_evidence),
        )
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or self.max_output_tokens < 1
        ):
            raise SemanticCompressionError(
                "max_output_tokens must be a positive integer"
            )
        if (
            isinstance(self.min_reduction_ratio, bool)
            or not isinstance(self.min_reduction_ratio, (int, float))
        ):
            raise SemanticCompressionError("min_reduction_ratio must be numeric")
        ratio = float(self.min_reduction_ratio)
        if not 0.0 < ratio < 1.0:
            raise SemanticCompressionError("min_reduction_ratio must be in (0,1)")
        object.__setattr__(self, "min_reduction_ratio", ratio)
        object.__setattr__(
            self,
            "compression_version",
            _text(self.compression_version, "compression_version", maximum=128),
        )
        if self.independent is not True:
            raise SemanticCompressionError(
                "semantic compression requires independent verification"
            )
        if self.authority_scope != SEMANTIC_COMPRESSION_AUTHORITY_SCOPE:
            raise SemanticCompressionError(
                "semantic compression cannot grant authority"
            )


@dataclass(frozen=True, slots=True)
class SemanticCompressionReceipt:
    accepted: bool
    reasons: tuple[str, ...]
    source_segment_ids: tuple[str, ...]
    source_content_digests: tuple[str, ...]
    source_tokens: int
    output_tokens: int
    candidate_digest: str
    verifier_id: str
    verifier_digest: str
    verifier_evidence: tuple[EvidenceRef, ...]
    derived_segment: ContextSegment | None
    compression_version: str
    authority_scope: str = SEMANTIC_COMPRESSION_AUTHORITY_SCOPE

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise SemanticCompressionError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise SemanticCompressionError(
                "reasons must contain non-empty strings"
            )
        if self.accepted != (self.derived_segment is not None):
            raise SemanticCompressionError(
                "accepted receipt must carry exactly one derived segment"
            )
        _sha(self.candidate_digest, "candidate_digest")
        _sha(self.verifier_digest, "verifier_digest")
        if self.authority_scope != SEMANTIC_COMPRESSION_AUTHORITY_SCOPE:
            raise SemanticCompressionError(
                "semantic compression receipt is non-authoritative"
            )

    @property
    def receipt_digest(self) -> str:
        return _digest(
            {
                "accepted": self.accepted,
                "reasons": list(self.reasons),
                "source_segment_ids": list(self.source_segment_ids),
                "source_content_digests": list(self.source_content_digests),
                "source_tokens": self.source_tokens,
                "output_tokens": self.output_tokens,
                "candidate_digest": self.candidate_digest,
                "verifier_id": self.verifier_id,
                "verifier_digest": self.verifier_digest,
                "verifier_evidence": [
                    {
                        "source": item.source,
                        "digest": item.digest,
                        "category": item.category,
                    }
                    for item in self.verifier_evidence
                ],
                "derived_segment_id": (
                    None
                    if self.derived_segment is None
                    else self.derived_segment.segment_id
                ),
                "derived_content_digest": (
                    None
                    if self.derived_segment is None
                    else self.derived_segment.content_digest
                ),
                "compression_version": self.compression_version,
                "authority_scope": self.authority_scope,
            }
        )


def qualify_semantic_compression(
    sources: Iterable[SemanticCompressionSource],
    proposal: SemanticCompressionProposal,
) -> SemanticCompressionReceipt:
    if not isinstance(proposal, SemanticCompressionProposal):
        raise TypeError("proposal must be SemanticCompressionProposal")
    if isinstance(sources, (str, bytes)):
        raise TypeError("sources must be an iterable of SemanticCompressionSource")
    source_rows = tuple(sources)
    if not source_rows or len(source_rows) > _MAX_SOURCES:
        raise SemanticCompressionError("sources must contain 1..128 entries")
    if any(
        not isinstance(item, SemanticCompressionSource)
        for item in source_rows
    ):
        raise TypeError("sources must contain SemanticCompressionSource values")

    source_rows = tuple(
        sorted(source_rows, key=lambda item: item.segment.segment_id)
    )
    if len({item.segment.segment_id for item in source_rows}) != len(source_rows):
        raise SemanticCompressionError("source segment ids must be unique")

    first = source_rows[0].segment
    reasons: list[str] = []
    for item in source_rows[1:]:
        segment = item.segment
        if segment.tenant_id != first.tenant_id:
            reasons.append("cross-tenant-compression")
        if segment.purpose != first.purpose:
            reasons.append("cross-purpose-compression")
        if segment.data_class != first.data_class:
            reasons.append("data-class-mismatch")
        if segment.retention_class != first.retention_class:
            reasons.append("retention-class-mismatch")

    source_tokens = sum(item.segment.token_estimate for item in source_rows)
    output_tokens = estimate_tokens(proposal.candidate_content)
    if output_tokens > proposal.max_output_tokens:
        reasons.append("output-token-budget")
    if output_tokens >= source_tokens:
        reasons.append("not-a-compression")
    required_reduction = int(source_tokens * proposal.min_reduction_ratio)
    if source_tokens - output_tokens < required_reduction:
        reasons.append("insufficient-reduction")

    required_facts = tuple(
        sorted({fact for item in source_rows for fact in item.required_facts})
    )
    preserved = set(proposal.preserved_facts)
    for fact in required_facts:
        if fact not in preserved or fact not in proposal.candidate_content:
            reasons.append("required-fact-not-preserved")
            break

    source_ids = tuple(item.segment.segment_id for item in source_rows)
    source_digests = tuple(item.segment.content_digest for item in source_rows)
    candidate_digest = sha256(
        proposal.candidate_content.encode("utf-8")
    ).hexdigest()
    normalized_reasons = tuple(sorted(set(reasons)))
    if normalized_reasons:
        return SemanticCompressionReceipt(
            accepted=False,
            reasons=normalized_reasons,
            source_segment_ids=source_ids,
            source_content_digests=source_digests,
            source_tokens=source_tokens,
            output_tokens=output_tokens,
            candidate_digest=candidate_digest,
            verifier_id=proposal.verifier_id,
            verifier_digest=proposal.verifier_digest,
            verifier_evidence=proposal.verifier_evidence,
            derived_segment=None,
            compression_version=proposal.compression_version,
        )

    identity_digest = _digest(
        {
            "source_segment_ids": list(source_ids),
            "source_content_digests": list(source_digests),
            "candidate_digest": candidate_digest,
            "verifier_id": proposal.verifier_id,
            "verifier_digest": proposal.verifier_digest,
            "compression_version": proposal.compression_version,
        }
    )
    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-semantic-compression:" + identity_digest,
        )
    )
    only_conversation = all(
        item.segment.kind in _CONVERSATION_KINDS for item in source_rows
    )
    kind = (
        ContextKind.CONVERSATION_SUMMARY
        if only_conversation
        else ContextKind.RETRIEVAL_EVIDENCE
    )
    provenance = tuple(
        sorted(
            {
                *(ref for item in source_rows for ref in item.segment.provenance),
                *(
                    f"semantic-source:{item.segment.segment_id}"
                    for item in source_rows
                ),
                *(
                    f"semantic-source-sha256:{item.segment.content_digest}"
                    for item in source_rows
                ),
                f"semantic-compression:{proposal.compression_version}",
                f"semantic-verifier:{proposal.verifier_id}",
                f"semantic-verifier-sha256:{proposal.verifier_digest}",
                *(
                    f"semantic-verifier-evidence:{item.category}:{item.digest}"
                    for item in proposal.verifier_evidence
                ),
            }
        )
    )
    derived = ContextSegment.from_content(
        segment_id=segment_id,
        kind=kind,
        source_type="semantic-compression",
        source_id="semantic-compression:" + identity_digest,
        content=proposal.candidate_content,
        trust_level=ContextTrust.DERIVED_UNTRUSTED,
        data_class=first.data_class,
        tenant_id=first.tenant_id,
        purpose=first.purpose,
        priority=max(item.segment.priority for item in source_rows),
        relevance=max(item.segment.relevance for item in source_rows),
        created_at=max(item.segment.created_at for item in source_rows),
        provenance=provenance,
        retention_class=first.retention_class,
        derived_from=source_ids,
        mandatory=False,
    )
    return SemanticCompressionReceipt(
        accepted=True,
        reasons=(),
        source_segment_ids=source_ids,
        source_content_digests=source_digests,
        source_tokens=source_tokens,
        output_tokens=output_tokens,
        candidate_digest=candidate_digest,
        verifier_id=proposal.verifier_id,
        verifier_digest=proposal.verifier_digest,
        verifier_evidence=proposal.verifier_evidence,
        derived_segment=derived,
        compression_version=proposal.compression_version,
    )


__all__ = [
    "SEMANTIC_COMPRESSION_AUTHORITY_SCOPE",
    "SEMANTIC_COMPRESSION_VERSION",
    "SemanticCompressionError",
    "SemanticCompressionProposal",
    "SemanticCompressionReceipt",
    "SemanticCompressionSource",
    "qualify_semantic_compression",
]
