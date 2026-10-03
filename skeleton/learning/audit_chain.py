"""Tamper-evident audit receipts for learned-model lifecycle decisions.

The repository already provides a content-addressed append-only evidence chain.
This module binds model-development events to that primitive with a strict
schema so training, evaluation, promotion, loading and rollback decisions can
be independently verified from immutable identities instead of mutable logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping

from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
    EvidenceCorruption,
    EvidenceNode,
    EvidenceStateBackend,
)


class LearningAuditError(RuntimeError):
    """A learned-model audit event is incomplete or inconsistent."""


EVENT_KINDS = frozenset(
    {
        "dataset_admitted",
        "training_started",
        "training_checkpointed",
        "training_completed",
        "evaluation_completed",
        "promotion_proposed",
        "promotion_approved",
        "artifact_load_admitted",
        "artifact_load_rejected",
        "rollback_proposed",
        "rollback_admitted",
        "rollback_rejected",
        "model_activated",
        "model_retired",
    }
)


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LearningAuditError("audit value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningAuditError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise LearningAuditError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise LearningAuditError(f"{name} must be lowercase sha256")
    return result


@dataclass(frozen=True, slots=True)
class LearningAuditEvent:
    event_id: str
    kind: str
    actor_principal: str
    subject_id: str
    subject_digest: str
    policy_digest: str
    decision: str
    evidence_root: str
    code_revision: str
    parent_event_id: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "event_id",
            "actor_principal",
            "subject_id",
            "decision",
            "code_revision",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(field_name, getattr(self, field_name)),
            )
        kind = _text("kind", self.kind)
        if kind not in EVENT_KINDS:
            raise LearningAuditError(f"unsupported learning audit event kind: {kind}")
        object.__setattr__(self, "kind", kind)

        for field_name in ("subject_digest", "policy_digest", "evidence_root"):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )

        if self.parent_event_id is not None:
            object.__setattr__(
                self,
                "parent_event_id",
                _text("parent_event_id", self.parent_event_id),
            )

        frozen = dict(self.details)
        if len(frozen) > 64:
            raise LearningAuditError("details contains too many fields")
        _stable_json(frozen)
        object.__setattr__(self, "details", frozen)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.learning_audit_event.v1",
            "event_id": self.event_id,
            "kind": self.kind,
            "actor_principal": self.actor_principal,
            "subject_id": self.subject_id,
            "subject_digest": self.subject_digest,
            "policy_digest": self.policy_digest,
            "decision": self.decision,
            "evidence_root": self.evidence_root,
            "code_revision": self.code_revision,
            "parent_event_id": self.parent_event_id,
            "details": dict(self.details),
        }

    @property
    def event_digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class LearningAuditReceipt:
    event_id: str
    event_digest: str
    sequence: int
    previous_root: str
    root_hash: str
    kind: str
    subject_id: str
    subject_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _text("event_id", self.event_id))
        object.__setattr__(self, "event_digest", _sha("event_digest", self.event_digest))
        for field_name in ("previous_root", "root_hash", "subject_digest"):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )
        object.__setattr__(self, "kind", _text("kind", self.kind))
        object.__setattr__(self, "subject_id", _text("subject_id", self.subject_id))
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise LearningAuditError("sequence must be a positive integer")


class LearningAuditLedger:
    """Typed learned-model lifecycle ledger over the repository evidence chain."""

    def __init__(
        self,
        backend: EvidenceStateBackend,
        *,
        namespace: str = "ai-learning-audit-v1",
        max_events: int = 1_000_000,
    ) -> None:
        self._chain = ContentAddressedEvidenceChain(
            backend,
            namespace=_text("namespace", namespace, maximum=128),
            max_events=max_events,
        )

    def append(self, event: LearningAuditEvent) -> LearningAuditReceipt:
        if not isinstance(event, LearningAuditEvent):
            raise TypeError("event must be LearningAuditEvent")
        committed = self._chain.snapshot()
        known_ids = {
            str(node.payload.get("event_id"))
            for node in committed
            if node.payload.get("event_id") is not None
        }
        if event.event_id in known_ids:
            raise LearningAuditError("event_id is already committed")
        if event.parent_event_id is not None and event.parent_event_id not in known_ids:
            raise LearningAuditError("parent_event_id is not committed")
        previous_root = self._chain.root_hash()
        payload = event.as_dict()
        payload["event_digest"] = event.event_digest
        node = self._chain.append(event.kind, payload)
        return LearningAuditReceipt(
            event_id=event.event_id,
            event_digest=event.event_digest,
            sequence=node.sequence,
            previous_root=previous_root,
            root_hash=node.node_hash,
            kind=event.kind,
            subject_id=event.subject_id,
            subject_digest=event.subject_digest,
        )

    def verify(self) -> bool:
        if not self._chain.verify():
            return False
        seen_event_ids: set[str] = set()
        for node in self._chain.snapshot():
            payload = dict(node.payload)
            try:
                event = LearningAuditEvent(
                    event_id=payload["event_id"],
                    kind=payload["kind"],
                    actor_principal=payload["actor_principal"],
                    subject_id=payload["subject_id"],
                    subject_digest=payload["subject_digest"],
                    policy_digest=payload["policy_digest"],
                    decision=payload["decision"],
                    evidence_root=payload["evidence_root"],
                    code_revision=payload["code_revision"],
                    parent_event_id=payload.get("parent_event_id"),
                    details=payload.get("details", {}),
                )
            except (KeyError, LearningAuditError, TypeError):
                return False
            if payload.get("event_digest") != event.event_digest:
                return False
            if event.event_id in seen_event_ids:
                return False
            if event.parent_event_id is not None and event.parent_event_id not in seen_event_ids:
                return False
            seen_event_ids.add(event.event_id)
        return True

    def verify_receipt(self, receipt: LearningAuditReceipt) -> bool:
        if not isinstance(receipt, LearningAuditReceipt):
            raise TypeError("receipt must be LearningAuditReceipt")
        try:
            node = self._chain.get_node(receipt.root_hash)
        except (EvidenceCorruption, ValueError):
            return False
        payload = dict(node.payload)
        return (
            node.sequence == receipt.sequence
            and node.previous_hash == receipt.previous_root
            and node.kind == receipt.kind
            and payload.get("event_id") == receipt.event_id
            and payload.get("event_digest") == receipt.event_digest
            and payload.get("subject_id") == receipt.subject_id
            and payload.get("subject_digest") == receipt.subject_digest
            and self._chain.verify_root(receipt.root_hash)
        )

    def root_hash(self) -> str:
        return self._chain.root_hash()

    def length(self) -> int:
        return self._chain.length()

    def snapshot(self) -> tuple[EvidenceNode, ...]:
        return self._chain.snapshot()


__all__ = [
    "EVENT_KINDS",
    "LearningAuditError",
    "LearningAuditEvent",
    "LearningAuditLedger",
    "LearningAuditReceipt",
]
