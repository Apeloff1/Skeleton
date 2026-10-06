"""Append-only temporal claim graph for VOL-012 Knowledge System.

Proposition identity, source/version, valid time, recorded time, confidence and
verification are separate dimensions. Contradictory claims survive as explicit
conflict sets. Mutations are exact-state fenced, evidence-bound, idempotent by
operation ID and append immutable revisions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import math
from typing import Iterable

from skeleton.contracts.canonical import EvidenceRef, canonical_json_bytes


KNOWLEDGE_SCHEMA_VERSION = 1
KNOWLEDGE_AUTHORITY_SCOPE = "knowledge-state-only"
_MAX_EVIDENCE = 256
_MAX_SUPERSEDES = 128


class KnowledgeStoreError(ValueError):
    """Knowledge state or a mutation violates the canonical contract."""


class VerificationState(str, Enum):
    UNVERIFIED = "unverified"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    REFUTED = "refuted"


class ClaimLifecycle(str, Enum):
    ACTIVE = "active"
    TOMBSTONED = "tombstoned"


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise KnowledgeStoreError(f"{field} must be normalized non-empty text")
    if len(value) > maximum:
        raise KnowledgeStoreError(f"{field} exceeds length limit")
    return value


def _sha(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise KnowledgeStoreError(f"{field} must be lowercase sha256")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KnowledgeStoreError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise KnowledgeStoreError(f"{field} must be finite and non-negative")
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise KnowledgeStoreError(f"{field} must be a positive integer")
    return value


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise KnowledgeStoreError("evidence must contain EvidenceRef")
    indexed: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise KnowledgeStoreError("evidence must contain EvidenceRef")
        _text(item.source, "evidence.source", maximum=2048)
        _sha(item.digest, "evidence.digest")
        _text(item.category, "evidence.category", maximum=128)
        indexed[(item.source, item.digest, item.category)] = item
    if not indexed:
        raise KnowledgeStoreError("mutations require evidence")
    if len(indexed) > _MAX_EVIDENCE:
        raise KnowledgeStoreError("evidence exceeds item limit")
    return tuple(indexed[key] for key in sorted(indexed))


def _evidence_payload(values: Iterable[EvidenceRef]) -> list[dict[str, str]]:
    return [
        {"source": item.source, "digest": item.digest, "category": item.category}
        for item in values
    ]


def _digest(payload: object) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class KnowledgeClaim:
    claim_id: str
    revision: int
    tenant_id: str
    scope_key: str
    subject: str
    predicate: str
    object_value: str
    source_id: str
    source_revision: str
    valid_from: float
    valid_to: float | None
    recorded_at: float
    confidence: float
    verification_state: VerificationState
    evidence: tuple[EvidenceRef, ...]
    lifecycle: ClaimLifecycle = ClaimLifecycle.ACTIVE
    supersedes_claim_ids: tuple[str, ...] = ()
    schema_version: int = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "claim_id",
            "tenant_id",
            "scope_key",
            "subject",
            "predicate",
            "object_value",
            "source_id",
            "source_revision",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self,
            "revision",
            _positive_int(self.revision, "revision"),
        )
        valid_from = _finite(self.valid_from, "valid_from")
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(
            self,
            "recorded_at",
            _finite(self.recorded_at, "recorded_at"),
        )
        if self.valid_to is not None:
            valid_to = _finite(self.valid_to, "valid_to")
            if valid_to <= valid_from:
                raise KnowledgeStoreError("valid_to must exceed valid_from")
            object.__setattr__(self, "valid_to", valid_to)
        confidence = _finite(self.confidence, "confidence")
        if confidence > 1.0:
            raise KnowledgeStoreError("confidence must be in [0,1]")
        object.__setattr__(self, "confidence", confidence)
        try:
            object.__setattr__(
                self,
                "verification_state",
                VerificationState(self.verification_state),
            )
        except ValueError as exc:
            raise KnowledgeStoreError("invalid verification_state") from exc
        object.__setattr__(self, "evidence", _evidence(self.evidence))
        try:
            object.__setattr__(
                self,
                "lifecycle",
                ClaimLifecycle(self.lifecycle),
            )
        except ValueError as exc:
            raise KnowledgeStoreError("invalid lifecycle") from exc
        supersedes = tuple(
            sorted(
                {
                    _text(item, "supersedes_claim_id")
                    for item in self.supersedes_claim_ids
                }
            )
        )
        if self.claim_id in supersedes:
            raise KnowledgeStoreError("claim cannot supersede itself")
        if len(supersedes) > _MAX_SUPERSEDES:
            raise KnowledgeStoreError("supersedes_claim_ids exceeds item limit")
        object.__setattr__(self, "supersedes_claim_ids", supersedes)
        if self.schema_version != KNOWLEDGE_SCHEMA_VERSION:
            raise KnowledgeStoreError("unsupported knowledge schema version")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "claim_id": self.claim_id,
            "revision": self.revision,
            "tenant_id": self.tenant_id,
            "scope_key": self.scope_key,
            "subject": self.subject,
            "predicate": self.predicate,
            "object_value": self.object_value,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "recorded_at": self.recorded_at,
            "confidence": self.confidence,
            "verification_state": self.verification_state.value,
            "evidence": _evidence_payload(self.evidence),
            "lifecycle": self.lifecycle.value,
            "supersedes_claim_ids": list(self.supersedes_claim_ids),
        }

    @property
    def revision_digest(self) -> str:
        return _digest(self.payload())

    @property
    def proposition_key(self) -> str:
        return _digest(
            {
                "tenant_id": self.tenant_id,
                "scope_key": self.scope_key,
                "subject": self.subject,
                "predicate": self.predicate,
            }
        )

    def valid_at(self, at: float) -> bool:
        instant = _finite(at, "at")
        return (
            self.lifecycle is ClaimLifecycle.ACTIVE
            and self.valid_from <= instant
            and (self.valid_to is None or instant < self.valid_to)
        )


@dataclass(frozen=True, slots=True)
class KnowledgeConflict:
    proposition_key: str
    claim_ids: tuple[str, ...]
    object_values: tuple[str, ...]
    verification_states: tuple[str, ...]
    conflict_digest: str

    def __post_init__(self) -> None:
        _sha(self.proposition_key, "proposition_key")
        _sha(self.conflict_digest, "conflict_digest")
        if len(self.claim_ids) < 2 or len(set(self.object_values)) < 2:
            raise KnowledgeStoreError(
                "knowledge conflict requires divergent claims"
            )


@dataclass(frozen=True, slots=True)
class KnowledgeSnapshot:
    tenant_id: str
    scope_key: str
    as_of: float
    claims: tuple[KnowledgeClaim, ...]
    conflicts: tuple[KnowledgeConflict, ...]
    store_digest: str
    authority_scope: str = KNOWLEDGE_AUTHORITY_SCOPE

    def __post_init__(self) -> None:
        _text(self.tenant_id, "tenant_id")
        _text(self.scope_key, "scope_key")
        object.__setattr__(self, "as_of", _finite(self.as_of, "as_of"))
        _sha(self.store_digest, "store_digest")
        if self.authority_scope != KNOWLEDGE_AUTHORITY_SCOPE:
            raise KnowledgeStoreError(
                "knowledge snapshot cannot grant execution authority"
            )

    @property
    def snapshot_digest(self) -> str:
        return _digest(
            {
                "tenant_id": self.tenant_id,
                "scope_key": self.scope_key,
                "as_of": self.as_of,
                "claims": [
                    {
                        "claim_id": item.claim_id,
                        "revision": item.revision,
                        "revision_digest": item.revision_digest,
                    }
                    for item in self.claims
                ],
                "conflicts": [
                    item.conflict_digest for item in self.conflicts
                ],
                "store_digest": self.store_digest,
                "authority_scope": self.authority_scope,
            }
        )


@dataclass(frozen=True, slots=True)
class ClaimMutationReceipt:
    operation_id: str
    request_digest: str
    claim_id: str
    revision: int
    revision_digest: str
    prior_store_digest: str
    next_store_digest: str
    evidence: tuple[EvidenceRef, ...]
    authority_scope: str = KNOWLEDGE_AUTHORITY_SCOPE

    def __post_init__(self) -> None:
        _text(self.operation_id, "operation_id")
        _text(self.claim_id, "claim_id")
        _positive_int(self.revision, "revision")
        for field in (
            "request_digest",
            "revision_digest",
            "prior_store_digest",
            "next_store_digest",
        ):
            _sha(getattr(self, field), field)
        object.__setattr__(self, "evidence", _evidence(self.evidence))
        if self.authority_scope != KNOWLEDGE_AUTHORITY_SCOPE:
            raise KnowledgeStoreError(
                "mutation receipt cannot grant external authority"
            )

    @property
    def receipt_digest(self) -> str:
        return _digest(
            {
                "operation_id": self.operation_id,
                "request_digest": self.request_digest,
                "claim_id": self.claim_id,
                "revision": self.revision,
                "revision_digest": self.revision_digest,
                "prior_store_digest": self.prior_store_digest,
                "next_store_digest": self.next_store_digest,
                "evidence": _evidence_payload(self.evidence),
                "authority_scope": self.authority_scope,
            }
        )


class TemporalKnowledgeStore:
    """Canonical semantics for an append-only temporal claim graph."""

    def __init__(self) -> None:
        self._history: dict[str, list[KnowledgeClaim]] = {}
        self._operations: dict[str, tuple[str, ClaimMutationReceipt]] = {}

    @property
    def store_digest(self) -> str:
        rows = [
            {
                "claim_id": claim_id,
                "revisions": [
                    {
                        "revision": item.revision,
                        "revision_digest": item.revision_digest,
                    }
                    for item in revisions
                ],
            }
            for claim_id, revisions in sorted(self._history.items())
        ]
        return _digest(
            {
                "schema_version": KNOWLEDGE_SCHEMA_VERSION,
                "claims": rows,
                "authority_scope": KNOWLEDGE_AUTHORITY_SCOPE,
            }
        )

    def _replay(
        self,
        operation_id: str,
        request_digest: str,
    ) -> ClaimMutationReceipt | None:
        prior = self._operations.get(operation_id)
        if prior is None:
            return None
        prior_request, receipt = prior
        if prior_request != request_digest:
            raise KnowledgeStoreError(
                "operation_id reused for a different knowledge mutation"
            )
        return receipt

    def _commit(
        self,
        claim: KnowledgeClaim,
        *,
        operation_id: str,
        request_digest: str,
        prior_store_digest: str,
        evidence: tuple[EvidenceRef, ...],
    ) -> ClaimMutationReceipt:
        self._history.setdefault(claim.claim_id, []).append(claim)
        next_digest = self.store_digest
        receipt = ClaimMutationReceipt(
            operation_id=operation_id,
            request_digest=request_digest,
            claim_id=claim.claim_id,
            revision=claim.revision,
            revision_digest=claim.revision_digest,
            prior_store_digest=prior_store_digest,
            next_store_digest=next_digest,
            evidence=evidence,
        )
        self._operations[operation_id] = (request_digest, receipt)
        return receipt

    def append(
        self,
        claim: KnowledgeClaim,
        *,
        operation_id: str,
        expected_store_digest: str,
        evidence: Iterable[EvidenceRef],
    ) -> ClaimMutationReceipt:
        if not isinstance(claim, KnowledgeClaim):
            raise TypeError("claim must be KnowledgeClaim")
        operation_id = _text(operation_id, "operation_id")
        expected_store_digest = _sha(
            expected_store_digest,
            "expected_store_digest",
        )
        mutation_evidence = _evidence(evidence)
        if claim.revision != 1:
            raise KnowledgeStoreError("new claim must start at revision 1")
        request_digest = _digest(
            {
                "kind": "append",
                "operation_id": operation_id,
                "expected_store_digest": expected_store_digest,
                "claim": claim.payload(),
                "evidence": _evidence_payload(mutation_evidence),
            }
        )
        replay = self._replay(operation_id, request_digest)
        if replay is not None:
            return replay
        if expected_store_digest != self.store_digest:
            raise KnowledgeStoreError("stale knowledge store digest")
        if claim.claim_id in self._history:
            raise KnowledgeStoreError("claim_id already exists")
        return self._commit(
            claim,
            operation_id=operation_id,
            request_digest=request_digest,
            prior_store_digest=expected_store_digest,
            evidence=mutation_evidence,
        )

    def head(self, claim_id: str) -> KnowledgeClaim:
        claim_id = _text(claim_id, "claim_id")
        revisions = self._history.get(claim_id)
        if not revisions:
            raise KnowledgeStoreError("unknown claim_id")
        return revisions[-1]

    def history(self, claim_id: str) -> tuple[KnowledgeClaim, ...]:
        claim_id = _text(claim_id, "claim_id")
        revisions = self._history.get(claim_id)
        if not revisions:
            raise KnowledgeStoreError("unknown claim_id")
        return tuple(revisions)

    def revise(
        self,
        claim_id: str,
        *,
        operation_id: str,
        expected_store_digest: str,
        expected_head_digest: str,
        recorded_at: float,
        source_revision: str,
        evidence: Iterable[EvidenceRef],
        object_value: str | None = None,
        valid_from: float | None = None,
        valid_to: float | None = None,
        confidence: float | None = None,
        verification_state: VerificationState | None = None,
        supersedes_claim_ids: Iterable[str] | None = None,
    ) -> ClaimMutationReceipt:
        claim_id = _text(claim_id, "claim_id")
        operation_id = _text(operation_id, "operation_id")
        expected_store_digest = _sha(
            expected_store_digest,
            "expected_store_digest",
        )
        expected_head_digest = _sha(
            expected_head_digest,
            "expected_head_digest",
        )
        mutation_evidence = _evidence(evidence)
        normalized_source_revision = _text(
            source_revision,
            "source_revision",
        )
        normalized_recorded_at = _finite(recorded_at, "recorded_at")
        normalized_object = (
            None
            if object_value is None
            else _text(object_value, "object_value")
        )
        normalized_valid_from = (
            None
            if valid_from is None
            else _finite(valid_from, "valid_from")
        )
        normalized_valid_to = (
            None
            if valid_to is None
            else _finite(valid_to, "valid_to")
        )
        normalized_confidence = (
            None
            if confidence is None
            else _finite(confidence, "confidence")
        )
        normalized_verification = (
            None
            if verification_state is None
            else VerificationState(verification_state)
        )
        normalized_supersedes = (
            None
            if supersedes_claim_ids is None
            else tuple(
                sorted(
                    {
                        _text(item, "supersedes_claim_id")
                        for item in supersedes_claim_ids
                    }
                )
            )
        )
        request_digest = _digest(
            {
                "kind": "revise",
                "operation_id": operation_id,
                "claim_id": claim_id,
                "expected_store_digest": expected_store_digest,
                "expected_head_digest": expected_head_digest,
                "recorded_at": normalized_recorded_at,
                "source_revision": normalized_source_revision,
                "object_value": normalized_object,
                "valid_from": normalized_valid_from,
                "valid_to": normalized_valid_to,
                "confidence": normalized_confidence,
                "verification_state": (
                    None
                    if normalized_verification is None
                    else normalized_verification.value
                ),
                "supersedes_claim_ids": (
                    None
                    if normalized_supersedes is None
                    else list(normalized_supersedes)
                ),
                "mutation_evidence": _evidence_payload(
                    mutation_evidence
                ),
            }
        )
        replay = self._replay(operation_id, request_digest)
        if replay is not None:
            return replay
        if expected_store_digest != self.store_digest:
            raise KnowledgeStoreError("stale knowledge store digest")
        current = self.head(claim_id)
        if expected_head_digest != current.revision_digest:
            raise KnowledgeStoreError("stale claim head digest")
        if current.lifecycle is ClaimLifecycle.TOMBSTONED:
            raise KnowledgeStoreError("tombstoned claim cannot be revised")
        if normalized_recorded_at < current.recorded_at:
            raise KnowledgeStoreError("recorded_at cannot move backward")

        next_claim = replace(
            current,
            revision=current.revision + 1,
            object_value=(
                current.object_value
                if normalized_object is None
                else normalized_object
            ),
            source_revision=normalized_source_revision,
            valid_from=(
                current.valid_from
                if normalized_valid_from is None
                else normalized_valid_from
            ),
            valid_to=(
                current.valid_to
                if normalized_valid_to is None
                else normalized_valid_to
            ),
            recorded_at=normalized_recorded_at,
            confidence=(
                current.confidence
                if normalized_confidence is None
                else normalized_confidence
            ),
            verification_state=(
                current.verification_state
                if normalized_verification is None
                else normalized_verification
            ),
            evidence=_evidence(
                (*current.evidence, *mutation_evidence)
            ),
            lifecycle=ClaimLifecycle.ACTIVE,
            supersedes_claim_ids=(
                current.supersedes_claim_ids
                if normalized_supersedes is None
                else normalized_supersedes
            ),
        )
        return self._commit(
            next_claim,
            operation_id=operation_id,
            request_digest=request_digest,
            prior_store_digest=expected_store_digest,
            evidence=mutation_evidence,
        )

    def tombstone(
        self,
        claim_id: str,
        *,
        operation_id: str,
        expected_store_digest: str,
        expected_head_digest: str,
        recorded_at: float,
        source_revision: str,
        evidence: Iterable[EvidenceRef],
    ) -> ClaimMutationReceipt:
        claim_id = _text(claim_id, "claim_id")
        operation_id = _text(operation_id, "operation_id")
        expected_store_digest = _sha(
            expected_store_digest,
            "expected_store_digest",
        )
        expected_head_digest = _sha(
            expected_head_digest,
            "expected_head_digest",
        )
        mutation_evidence = _evidence(evidence)
        normalized_source_revision = _text(
            source_revision,
            "source_revision",
        )
        normalized_recorded_at = _finite(recorded_at, "recorded_at")
        request_digest = _digest(
            {
                "kind": "tombstone",
                "operation_id": operation_id,
                "claim_id": claim_id,
                "expected_store_digest": expected_store_digest,
                "expected_head_digest": expected_head_digest,
                "recorded_at": normalized_recorded_at,
                "source_revision": normalized_source_revision,
                "mutation_evidence": _evidence_payload(
                    mutation_evidence
                ),
            }
        )
        replay = self._replay(operation_id, request_digest)
        if replay is not None:
            return replay
        if expected_store_digest != self.store_digest:
            raise KnowledgeStoreError("stale knowledge store digest")
        current = self.head(claim_id)
        if expected_head_digest != current.revision_digest:
            raise KnowledgeStoreError("stale claim head digest")
        if current.lifecycle is ClaimLifecycle.TOMBSTONED:
            raise KnowledgeStoreError("claim is already tombstoned")
        if normalized_recorded_at < current.recorded_at:
            raise KnowledgeStoreError("recorded_at cannot move backward")
        next_claim = replace(
            current,
            revision=current.revision + 1,
            source_revision=normalized_source_revision,
            recorded_at=normalized_recorded_at,
            evidence=_evidence(
                (*current.evidence, *mutation_evidence)
            ),
            lifecycle=ClaimLifecycle.TOMBSTONED,
        )
        return self._commit(
            next_claim,
            operation_id=operation_id,
            request_digest=request_digest,
            prior_store_digest=expected_store_digest,
            evidence=mutation_evidence,
        )

    def snapshot(
        self,
        *,
        tenant_id: str,
        scope_key: str,
        as_of: float,
    ) -> KnowledgeSnapshot:
        tenant_id = _text(tenant_id, "tenant_id")
        scope_key = _text(scope_key, "scope_key")
        instant = _finite(as_of, "as_of")
        selected: list[KnowledgeClaim] = []
        for revisions in self._history.values():
            eligible = [
                item
                for item in revisions
                if item.recorded_at <= instant
                and item.tenant_id == tenant_id
                and item.scope_key == scope_key
            ]
            if not eligible:
                continue
            head_at_time = max(
                eligible,
                key=lambda item: (
                    item.revision,
                    item.recorded_at,
                    item.revision_digest,
                ),
            )
            if head_at_time.valid_at(instant):
                selected.append(head_at_time)
        selected.sort(
            key=lambda item: (
                item.subject,
                item.predicate,
                item.object_value,
                item.claim_id,
                item.revision,
            )
        )

        groups: dict[str, list[KnowledgeClaim]] = {}
        for claim in selected:
            groups.setdefault(claim.proposition_key, []).append(claim)
        conflicts: list[KnowledgeConflict] = []
        for proposition_key, claims in sorted(groups.items()):
            object_values = tuple(
                sorted({item.object_value for item in claims})
            )
            if len(object_values) < 2:
                continue
            claim_ids = tuple(
                sorted(item.claim_id for item in claims)
            )
            states = tuple(
                f"{item.claim_id}:{item.verification_state.value}"
                for item in sorted(
                    claims,
                    key=lambda item: item.claim_id,
                )
            )
            conflict_digest = _digest(
                {
                    "proposition_key": proposition_key,
                    "claim_ids": list(claim_ids),
                    "object_values": list(object_values),
                    "verification_states": list(states),
                }
            )
            conflicts.append(
                KnowledgeConflict(
                    proposition_key=proposition_key,
                    claim_ids=claim_ids,
                    object_values=object_values,
                    verification_states=states,
                    conflict_digest=conflict_digest,
                )
            )
        return KnowledgeSnapshot(
            tenant_id=tenant_id,
            scope_key=scope_key,
            as_of=instant,
            claims=tuple(selected),
            conflicts=tuple(conflicts),
            store_digest=self.store_digest,
        )


__all__ = [
    "KNOWLEDGE_AUTHORITY_SCOPE",
    "KNOWLEDGE_SCHEMA_VERSION",
    "ClaimLifecycle",
    "ClaimMutationReceipt",
    "KnowledgeClaim",
    "KnowledgeConflict",
    "KnowledgeSnapshot",
    "KnowledgeStoreError",
    "TemporalKnowledgeStore",
    "VerificationState",
]
