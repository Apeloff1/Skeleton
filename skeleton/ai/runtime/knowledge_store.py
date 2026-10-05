"""Deterministic append-only knowledge claim store.

Contradictory claims coexist. Confidence is an observation, never verification.
Verification requires explicit evidence and is represented independently.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from typing import Any, Iterable
from skeleton.contracts.canonical import canonical_json_bytes

KNOWLEDGE_STORE_SCHEMA_VERSION = 1

class KnowledgeStoreError(ValueError):
    """Knowledge state violates canonical store invariants."""

def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise KnowledgeStoreError(f"{field} must be normalized non-empty text")
    return value

def _digest(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    source: str
    content_digest: str
    observed_at: str
    def __post_init__(self) -> None:
        _text(self.source, "source"); _text(self.observed_at, "observed_at")
        if not isinstance(self.content_digest, str) or len(self.content_digest) != 64:
            raise KnowledgeStoreError("content_digest must be sha256 hex")
        try: int(self.content_digest, 16)
        except ValueError as exc: raise KnowledgeStoreError("content_digest must be sha256 hex") from exc
    def payload(self) -> dict[str, str]:
        return {"source": self.source, "content_digest": self.content_digest, "observed_at": self.observed_at}
    @property
    def evidence_id(self) -> str: return _digest(self.payload())

@dataclass(frozen=True, slots=True)
class Claim:
    subject: str
    predicate: str
    value: Any
    scope: str
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: float | None = None
    def __post_init__(self) -> None:
        for field in ("subject", "predicate", "scope"): _text(getattr(self, field), field)
        if self.valid_from is not None: _text(self.valid_from, "valid_from")
        if self.valid_to is not None: _text(self.valid_to, "valid_to")
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
                raise KnowledgeStoreError("confidence must be numeric")
            if not 0.0 <= float(self.confidence) <= 1.0:
                raise KnowledgeStoreError("confidence must be between 0 and 1")
            object.__setattr__(self, "confidence", float(self.confidence))
        canonical_json_bytes(self.value)
    def payload(self) -> dict[str, Any]:
        return {"subject": self.subject, "predicate": self.predicate, "value": self.value, "scope": self.scope, "valid_from": self.valid_from, "valid_to": self.valid_to, "confidence": self.confidence}
    @property
    def claim_id(self) -> str: return _digest(self.payload())

@dataclass(frozen=True, slots=True)
class ClaimAssertion:
    claim: Claim
    evidence: tuple[EvidenceRecord, ...]
    verified: bool = False
    def __post_init__(self) -> None:
        if not isinstance(self.claim, Claim): raise TypeError("claim must be Claim")
        if not isinstance(self.evidence, tuple) or any(not isinstance(x, EvidenceRecord) for x in self.evidence):
            raise TypeError("evidence must be a tuple of EvidenceRecord")
        if self.verified and not self.evidence: raise KnowledgeStoreError("verified claims require explicit evidence")
    def payload(self) -> dict[str, Any]:
        return {"claim": self.claim.payload(), "evidence_ids": sorted(x.evidence_id for x in self.evidence), "verified": self.verified}
    @property
    def assertion_id(self) -> str: return _digest(self.payload())

@dataclass(frozen=True, slots=True)
class KnowledgeSnapshot:
    assertions: tuple[ClaimAssertion, ...]
    @property
    def snapshot_digest(self) -> str:
        return _digest({"schema_version": KNOWLEDGE_STORE_SCHEMA_VERSION, "assertion_ids": sorted(x.assertion_id for x in self.assertions)})

class KnowledgeStore:
    """Canonical primitive; persistence adapters can replay assertions."""
    def __init__(self, assertions: Iterable[ClaimAssertion] = ()) -> None:
        self._assertions: dict[str, ClaimAssertion] = {}
        for assertion in assertions: self.append(assertion)
    def append(self, assertion: ClaimAssertion) -> str:
        if not isinstance(assertion, ClaimAssertion): raise TypeError("assertion must be ClaimAssertion")
        existing = self._assertions.get(assertion.assertion_id)
        if existing is not None and existing != assertion: raise KnowledgeStoreError("assertion identity collision")
        self._assertions[assertion.assertion_id] = assertion
        return assertion.assertion_id
    def assertions(self) -> tuple[ClaimAssertion, ...]:
        return tuple(self._assertions[key] for key in sorted(self._assertions))
    def claims_for(self, subject: str, predicate: str, *, scope: str | None = None) -> tuple[ClaimAssertion, ...]:
        _text(subject, "subject"); _text(predicate, "predicate")
        if scope is not None: _text(scope, "scope")
        return tuple(item for item in self.assertions() if item.claim.subject == subject and item.claim.predicate == predicate and (scope is None or item.claim.scope == scope))
    def snapshot(self) -> KnowledgeSnapshot: return KnowledgeSnapshot(self.assertions())

__all__ = ["KNOWLEDGE_STORE_SCHEMA_VERSION","Claim","ClaimAssertion","EvidenceRecord","KnowledgeSnapshot","KnowledgeStore","KnowledgeStoreError"]
