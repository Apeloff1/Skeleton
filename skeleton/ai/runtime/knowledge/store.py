"""Deterministic evidence-bound knowledge claim store.

Confidence expresses belief strength. Verification is a separate evidence state:
high confidence can never manufacture verification. Conflicting claim values are
retained and surfaced until an explicit, evidence-backed resolution is recorded.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from skeleton.contracts.canonical import CanonicalContractError, canonical_json_bytes

STATE_VERSION = 1


class VerificationState(str, Enum):
    UNVERIFIED = "unverified"
    CORROBORATED = "corroborated"
    VERIFIED = "verified"
    REJECTED = "rejected"


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _digest(name: str, value: Any) -> str:
    value = _text(name, value)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("confidence must be a finite number")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    return value


@dataclass(frozen=True, slots=True)
class KnowledgeEvidence:
    source: str
    digest: str
    observed_at: float

    def __post_init__(self) -> None:
        _text("source", self.source)
        _digest("digest", self.digest)
        if isinstance(self.observed_at, bool) or not isinstance(self.observed_at, (int, float)):
            raise ValueError("observed_at must be finite")
        if not math.isfinite(float(self.observed_at)):
            raise ValueError("observed_at must be finite")

    def to_dict(self) -> Dict[str, Any]:
        return {"source": self.source, "digest": self.digest, "observed_at": self.observed_at}


@dataclass(frozen=True, slots=True)
class KnowledgeClaim:
    claim_id: str
    scope_key: str
    subject: str
    predicate: str
    value_digest: str
    confidence: float
    verification: VerificationState
    evidence: Tuple[KnowledgeEvidence, ...]
    recorded_at: float

    def __post_init__(self) -> None:
        for name in ("claim_id", "scope_key", "subject", "predicate"):
            _text(name, getattr(self, name))
        _digest("value_digest", self.value_digest)
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        try:
            state = VerificationState(self.verification)
        except ValueError as exc:
            raise ValueError("verification state is invalid") from exc
        object.__setattr__(self, "verification", state)
        if isinstance(self.recorded_at, bool) or not isinstance(self.recorded_at, (int, float)):
            raise ValueError("recorded_at must be finite")
        if not math.isfinite(float(self.recorded_at)):
            raise ValueError("recorded_at must be finite")
        canonical_evidence = tuple(sorted(set(self.evidence), key=lambda e: (e.source, e.digest, e.observed_at)))
        object.__setattr__(self, "evidence", canonical_evidence)
        if state in (VerificationState.CORROBORATED, VerificationState.VERIFIED) and not canonical_evidence:
            raise ValueError("verified knowledge requires evidence")

    @property
    def key(self) -> Tuple[str, str, str]:
        return self.scope_key, self.subject, self.predicate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "scope_key": self.scope_key,
            "subject": self.subject,
            "predicate": self.predicate,
            "value_digest": self.value_digest,
            "confidence": self.confidence,
            "verification": self.verification.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "recorded_at": self.recorded_at,
        }

    @property
    def identity(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class KnowledgeView:
    claims: Tuple[KnowledgeClaim, ...]
    conflicting: bool
    snapshot_digest: str


class KnowledgeStore:
    """Thread-safe append-only claim store with deterministic snapshots."""

    def __init__(self) -> None:
        self._claims: Dict[str, KnowledgeClaim] = {}
        self._lock = RLock()

    def record(self, claim: KnowledgeClaim) -> str:
        if not isinstance(claim, KnowledgeClaim):
            raise TypeError("claim must be KnowledgeClaim")
        with self._lock:
            existing = self._claims.get(claim.claim_id)
            if existing is not None:
                if existing.identity != claim.identity:
                    raise ValueError("claim_id collision with different content")
                return existing.identity
            self._claims[claim.claim_id] = claim
            return claim.identity

    def get(self, claim_id: str) -> Optional[KnowledgeClaim]:
        with self._lock:
            return self._claims.get(claim_id)

    def query(self, *, scope_key: str, subject: str, predicate: str) -> KnowledgeView:
        key = (_text("scope_key", scope_key), _text("subject", subject), _text("predicate", predicate))
        with self._lock:
            claims = tuple(sorted((c for c in self._claims.values() if c.key == key), key=lambda c: c.claim_id))
        values = {c.value_digest for c in claims if c.verification is not VerificationState.REJECTED}
        payload = {"key": list(key), "claims": [c.to_dict() for c in claims]}
        return KnowledgeView(
            claims=claims,
            conflicting=len(values) > 1,
            snapshot_digest=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            claims = sorted(self._claims.values(), key=lambda c: c.claim_id)
        body = {"version": STATE_VERSION, "claims": [c.to_dict() for c in claims]}
        return {**body, "snapshot_digest": hashlib.sha256(canonical_json_bytes(body)).hexdigest()}

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> "KnowledgeStore":
        if not isinstance(payload, Mapping) or payload.get("version") != STATE_VERSION:
            raise ValueError("unsupported knowledge snapshot")
        rows = payload.get("claims")
        supplied = payload.get("snapshot_digest")
        if not isinstance(rows, list) or not isinstance(supplied, str):
            raise ValueError("malformed knowledge snapshot")
        body = {"version": STATE_VERSION, "claims": rows}
        try:
            actual_digest = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        except CanonicalContractError as exc:
            raise ValueError("knowledge snapshot is not strict canonical JSON") from exc
        if actual_digest != supplied:
            raise ValueError("knowledge snapshot digest mismatch")
        store = cls()
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("knowledge claim must be a mapping")
            raw_evidence = row.get("evidence")
            if not isinstance(raw_evidence, list):
                raise ValueError("knowledge evidence must be a list")
            evidence = tuple(KnowledgeEvidence(
                source=str(item.get("source") or ""),
                digest=str(item.get("digest") or ""),
                observed_at=item.get("observed_at"),
            ) for item in raw_evidence if isinstance(item, Mapping))
            if len(evidence) != len(raw_evidence):
                raise ValueError("knowledge evidence must contain mappings")
            store.record(KnowledgeClaim(
                claim_id=str(row.get("claim_id") or ""),
                scope_key=str(row.get("scope_key") or ""),
                subject=str(row.get("subject") or ""),
                predicate=str(row.get("predicate") or ""),
                value_digest=str(row.get("value_digest") or ""),
                confidence=row.get("confidence"),
                verification=VerificationState(str(row.get("verification") or "")),
                evidence=evidence,
                recorded_at=row.get("recorded_at"),
            ))
        return store
