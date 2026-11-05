"""Grounded span citation verifier with exact source-digest and scope checks.

Citations are observational provenance, not proof that claims are true.
A model may cite a genuine span and still make an incorrect inference.
Every source text must originate in the existing independently approved
signed-source channel; no model-provided path or title becomes file authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping, Sequence

from .contracts import ContractHold, digest, exact_integer, fingerprint, identifier, text


@dataclass(frozen=True, slots=True)
class CitationSpan:
    citation_id: str
    source_id: str
    source_sha256: str
    scope_sha256: str
    start_byte: int
    end_byte: int
    quote_sha256: str

    def __post_init__(self):
        identifier(self.citation_id, "citation")
        identifier(self.source_id, "source")
        digest(self.source_sha256)
        digest(self.scope_sha256)
        digest(self.quote_sha256)
        exact_integer(self.start_byte, maximum=2**40)
        exact_integer(self.end_byte, maximum=2**40)
        if self.end_byte <= self.start_byte:
            raise ContractHold("citation spans must be nonempty")


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    claim_id: str
    statement: str
    citations: tuple[CitationSpan, ...]
    support_required: bool = True

    def __post_init__(self):
        identifier(self.claim_id, "claim")
        text(self.statement, maximum_bytes=32768)
        if type(self.citations) is not tuple or len(self.citations) > 32:
            raise ContractHold("claim must have finite typed citations")
        if any(not isinstance(s, CitationSpan) for s in self.citations):
            raise ContractHold("untyped citation")
        if type(self.support_required) is not bool:
            raise ContractHold("host support policy must be strict boolean")


@dataclass(frozen=True, slots=True)
class ClaimAudit:
    claim_id: str
    evidence_valid: bool
    unresolved: tuple[str, ...]
    matched_sources: tuple[str, ...]
    source_fingerprints: tuple[str, ...]
    model_statement_fingerprint: str

    def __post_init__(self):
        identifier(self.claim_id)
        if type(self.evidence_valid) is not bool:
            raise ContractHold("typed evidence verdict required")
        if self.evidence_valid and self.unresolved:
            raise ContractHold("valid evidence claim contains unresolved failures")

    def to_record(self):
        return {
            "schema": "jeeves.fabric.claim_audit.v1",
            "claim_id": self.claim_id, "evidence_valid": self.evidence_valid,
            "unresolved": list(self.unresolved),
            "matched_sources": list(self.matched_sources),
            "source_fingerprints": list(self.source_fingerprints),
            "model_statement_fingerprint": self.model_statement_fingerprint,
            "semantic_truth_certified": False,
            "release_certified": False,
        }


def validate_claim(
    claim: EvidenceClaim, *,
    sources: Mapping[str, bytes],
    source_digests: Mapping[str, str],
    scope_sha256: str,
    maximum_source_bytes: int = 1048576,
) -> ClaimAudit:
    if not isinstance(claim, EvidenceClaim):
        raise ContractHold("typed claim required")
    digest(scope_sha256)
    exact_integer(maximum_source_bytes, minimum=1, maximum=1048576)
    if type(sources) is not dict or type(source_digests) is not dict:
        raise ContractHold("host-bound source byte mappings required")
    if len(sources) > 128 or len(source_digests) > 128:
        raise ContractHold("source inventory exceeds finite bound")
    reasons = []
    matches = set()
    hashes = set()
    if claim.support_required and not claim.citations:
        reasons.append("no_citations")
    ids = set()
    for citation in claim.citations:
        if citation.citation_id in ids:
            reasons.append("duplicate_citation_id")
            continue
        ids.add(citation.citation_id)
        if citation.scope_sha256 != scope_sha256:
            reasons.append("foreign_principal_citation")
            continue
        raw = sources.get(citation.source_id)
        expected = source_digests.get(citation.source_id)
        if type(raw) is not bytes or type(expected) is not str:
            reasons.append("source_unavailable")
            continue
        if not 1 <= len(raw) <= maximum_source_bytes:
            reasons.append("source_bytes_out_of_bounds")
            continue
        digest(expected)
        observed = sha256(raw).hexdigest()
        if expected != observed or expected != citation.source_sha256:
            reasons.append("source_digest_changed")
            continue
        if citation.end_byte > len(raw):
            reasons.append("citation_offset_out_of_range")
            continue
        quote = raw[citation.start_byte:citation.end_byte]
        try:
            quote.decode("utf-8", "strict")
        except UnicodeError:
            reasons.append("citation_splits_utf8")
            continue
        if sha256(quote).hexdigest() != citation.quote_sha256:
            reasons.append("citation_quote_mismatch")
            continue
        matches.add(citation.source_id)
        hashes.add(citation.source_sha256)
    return ClaimAudit(
        claim_id=claim.claim_id,
        evidence_valid=not reasons,
        unresolved=tuple(reasons),
        matched_sources=tuple(sorted(matches)),
        source_fingerprints=tuple(sorted(hashes)),
        model_statement_fingerprint=sha256(
            claim.statement.encode("utf-8", "strict")
        ).hexdigest(),
    )


def audit_claims(
    claims: Sequence[EvidenceClaim], *,
    sources: Mapping[str, bytes],
    source_digests: Mapping[str, str],
    scope_sha256: str,
    maximum_claims: int = 128,
) -> dict[str, object]:
    exact_integer(maximum_claims, minimum=1, maximum=1024)
    if type(claims) not in (tuple, list) or len(claims) > maximum_claims:
        raise ContractHold("unbounded citation audit")
    if len({c.claim_id for c in claims}) != len(claims):
        raise ContractHold("duplicate claim identity")
    results = tuple(validate_claim(
        claim, sources=sources,
        source_digests=source_digests,
        scope_sha256=scope_sha256,
    ) for claim in claims)
    return {
        "schema": "jeeves.fabric.citation_audit.v1",
        "claims": [result.to_record() for result in results],
        "verified_span_count": sum(len(result.matched_sources) for result in results),
        "held_claims": sum(not result.evidence_valid for result in results),
        "all_spans_bound": all(result.evidence_valid for result in results),
        "source_legal_rights_proved": False,
        "semantic_truth_certified": False,
    }


__all__ = ["CitationSpan", "EvidenceClaim", "ClaimAudit",
           "validate_claim", "audit_claims"]
