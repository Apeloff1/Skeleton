"""Fail-closed evidence cards for masterplan VOL-221..VOL-224.

Cards are immutable disclosures.  They never grant runtime authority: callers
must obtain authority from the canonical control plane independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .contracts import sha256_json


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _digest(value: object, name: str) -> str:
    value = _text(value, name)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


def _unique(values: Iterable[str], name: str) -> tuple[str, ...]:
    result = tuple(_text(v, name) for v in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must be unique")
    return result


class ClaimKind(str, Enum):
    MEASURED = "measured"
    QUALITATIVE = "qualitative"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    artifact_digest: str
    revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "artifact_digest", _digest(self.artifact_digest, "artifact_digest"))
        object.__setattr__(self, "revision", _text(self.revision, "revision"))


@dataclass(frozen=True, slots=True)
class CardClaim:
    claim_id: str
    statement: str
    kind: ClaimKind
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _text(self.claim_id, "claim_id"))
        object.__setattr__(self, "statement", _text(self.statement, "statement"))
        if not isinstance(self.kind, ClaimKind):
            raise TypeError("kind must be ClaimKind")
        object.__setattr__(self, "evidence_ids", _unique(self.evidence_ids, "evidence_id"))
        if self.kind is ClaimKind.MEASURED and not self.evidence_ids:
            raise ValueError("measured claims require evidence")


@dataclass(frozen=True, slots=True)
class ModelCard:
    model_id: str
    model_digest: str
    eval_revision: str
    claims: tuple[CardClaim, ...]
    evidence: tuple[EvidenceRef, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        object.__setattr__(self, "model_digest", _digest(self.model_digest, "model_digest"))
        object.__setattr__(self, "eval_revision", _text(self.eval_revision, "eval_revision"))
        object.__setattr__(self, "limitations", _unique(self.limitations, "limitation"))
        _validate_claim_evidence(self.claims, self.evidence)
        if not self.limitations:
            raise ValueError("model card must disclose limitations")

    @property
    def identity(self) -> str:
        return sha256_json(_card_payload(self))


@dataclass(frozen=True, slots=True)
class DatasetCard:
    dataset_id: str
    dataset_digest: str
    provenance: tuple[str, ...]
    excluded_provenance: tuple[str, ...]
    unknown_provenance: tuple[str, ...]
    sensitive_attributes: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text(self.dataset_id, "dataset_id"))
        object.__setattr__(self, "dataset_digest", _digest(self.dataset_digest, "dataset_digest"))
        for name in ("provenance", "excluded_provenance", "unknown_provenance", "sensitive_attributes"):
            object.__setattr__(self, name, _unique(getattr(self, name), name))
        _evidence_map(self.evidence)

    @property
    def identity(self) -> str:
        return sha256_json(_card_payload(self))


@dataclass(frozen=True, slots=True)
class ToolCard:
    tool_id: str
    implementation_digest: str
    owner: str
    declared_capabilities: tuple[str, ...]
    risks: tuple[str, ...]
    security_review: EvidenceRef
    authority_grants: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_id", _text(self.tool_id, "tool_id"))
        object.__setattr__(self, "implementation_digest", _digest(self.implementation_digest, "implementation_digest"))
        object.__setattr__(self, "owner", _text(self.owner, "owner"))
        object.__setattr__(self, "declared_capabilities", _unique(self.declared_capabilities, "capability"))
        object.__setattr__(self, "risks", _unique(self.risks, "risk"))
        object.__setattr__(self, "authority_grants", _unique(self.authority_grants, "authority_grant"))
        if self.authority_grants:
            raise ValueError("tool cards are disclosure-only and cannot grant authority")
        if not self.risks:
            raise ValueError("tool card must disclose risks")

    @property
    def identity(self) -> str:
        return sha256_json(_card_payload(self))


@dataclass(frozen=True, slots=True)
class AgentCard:
    agent_id: str
    definition_digest: str
    default_authority: tuple[str, ...]
    optional_delegated_grants: tuple[str, ...]
    evaluation: EvidenceRef
    claims: tuple[CardClaim, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _text(self.agent_id, "agent_id"))
        object.__setattr__(self, "definition_digest", _digest(self.definition_digest, "definition_digest"))
        object.__setattr__(self, "default_authority", _unique(self.default_authority, "default_authority"))
        object.__setattr__(self, "optional_delegated_grants", _unique(self.optional_delegated_grants, "optional_delegated_grant"))
        if set(self.default_authority) & set(self.optional_delegated_grants):
            raise ValueError("default and delegated authority disclosures must be distinct")
        _validate_claim_evidence(self.claims, (self.evaluation,))

    @property
    def identity(self) -> str:
        return sha256_json(_card_payload(self))


def _evidence_map(evidence: Sequence[EvidenceRef]) -> Mapping[str, EvidenceRef]:
    result: dict[str, EvidenceRef] = {}
    for item in evidence:
        if item.evidence_id in result and result[item.evidence_id] != item:
            raise ValueError("evidence id collision")
        result[item.evidence_id] = item
    return result


def _validate_claim_evidence(claims: Sequence[CardClaim], evidence: Sequence[EvidenceRef]) -> None:
    ids = [claim.claim_id for claim in claims]
    if len(ids) != len(set(ids)):
        raise ValueError("claim ids must be unique")
    available = _evidence_map(evidence)
    for claim in claims:
        missing = set(claim.evidence_ids) - set(available)
        if missing:
            raise ValueError(f"claim references unknown evidence: {sorted(missing)}")


def _card_payload(card: object) -> dict[str, object]:
    if isinstance(card, ModelCard):
        return {
            "schema": "skeleton.model-card.v1", "model_id": card.model_id,
            "model_digest": card.model_digest, "eval_revision": card.eval_revision,
            "claims": [_claim_payload(c) for c in card.claims],
            "evidence": [_evidence_payload(e) for e in card.evidence],
            "limitations": list(card.limitations),
        }
    if isinstance(card, DatasetCard):
        return {
            "schema": "skeleton.dataset-card.v1", "dataset_id": card.dataset_id,
            "dataset_digest": card.dataset_digest, "provenance": list(card.provenance),
            "excluded_provenance": list(card.excluded_provenance),
            "unknown_provenance": list(card.unknown_provenance),
            "sensitive_attributes": list(card.sensitive_attributes),
            "evidence": [_evidence_payload(e) for e in card.evidence],
        }
    if isinstance(card, ToolCard):
        return {
            "schema": "skeleton.tool-card.v1", "tool_id": card.tool_id,
            "implementation_digest": card.implementation_digest, "owner": card.owner,
            "declared_capabilities": list(card.declared_capabilities), "risks": list(card.risks),
            "security_review": _evidence_payload(card.security_review), "authority_grants": [],
        }
    if isinstance(card, AgentCard):
        return {
            "schema": "skeleton.agent-card.v1", "agent_id": card.agent_id,
            "definition_digest": card.definition_digest,
            "default_authority": list(card.default_authority),
            "optional_delegated_grants": list(card.optional_delegated_grants),
            "evaluation": _evidence_payload(card.evaluation),
            "claims": [_claim_payload(c) for c in card.claims],
        }
    raise TypeError("unsupported card type")


def _claim_payload(claim: CardClaim) -> dict[str, object]:
    return {"claim_id": claim.claim_id, "statement": claim.statement, "kind": claim.kind.value, "evidence_ids": list(claim.evidence_ids)}


def _evidence_payload(evidence: EvidenceRef) -> dict[str, str]:
    return {"evidence_id": evidence.evidence_id, "artifact_digest": evidence.artifact_digest, "revision": evidence.revision}


class CardRegistry:
    """Content-addressed registry with collision and stale-revision protection."""

    def __init__(self) -> None:
        self._cards: dict[tuple[str, str], tuple[str, object]] = {}

    def publish(self, kind: str, subject_id: str, card: object) -> str:
        kind = _text(kind, "kind")
        subject_id = _text(subject_id, "subject_id")
        identity = getattr(card, "identity", None)
        if not isinstance(identity, str):
            raise TypeError("card must expose deterministic identity")
        key = (kind, subject_id)
        prior = self._cards.get(key)
        if prior is not None and prior[0] != identity:
            raise ValueError("card replacement requires explicit versioned subject identity")
        self._cards[key] = (identity, card)
        return identity

    def get(self, kind: str, subject_id: str) -> object | None:
        item = self._cards.get((kind, subject_id))
        return None if item is None else item[1]
