"""Tamper-evident audit receipts for learned-model lifecycle decisions.

This module binds model-development events to the repository evidence chain
with strict immutable identities.  Appends are serialized at the typed ledger
boundary, event ids are immutable bindings, parent custody is session/subject
local, and every receipt can be checked against a content-addressed ledger
snapshot rather than a mutable log position.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
import hashlib
import json
import math
import threading
from types import MappingProxyType
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
        raise LearningAuditError(
            "audit value is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(
        _stable_json(value).encode("utf-8")
    ).hexdigest()


def _text(
    name: str,
    value: object,
    *,
    maximum: int = 2048,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningAuditError(
            f"{name} must be non-empty text"
        )
    result = value.strip()
    if len(result) > maximum:
        raise LearningAuditError(
            f"{name} exceeds {maximum} characters"
        )
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise LearningAuditError(
            f"{name} must be lowercase sha256"
        )
    return result


def _positive_int(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise LearningAuditError(
            f"{name} must be a positive integer"
        )
    return value


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        _stable_json(value)
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LearningAuditError(
                "audit details contain non-finite number"
            )
        return value
    if isinstance(value, MappingABC):
        frozen: dict[str, object] = {}
        for raw_key, item in value.items():
            key = _text("details key", raw_key, maximum=128)
            if key in frozen:
                raise LearningAuditError(
                    "details keys collide after normalization"
                )
            frozen[key] = _freeze_json(item)
        return MappingProxyType(dict(sorted(frozen.items())))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise LearningAuditError(
        "audit details contain unsupported non-JSON value"
    )


def _thaw_json(value: object) -> object:
    if isinstance(value, MappingABC):
        return {
            key: _thaw_json(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


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
            raise LearningAuditError(
                f"unsupported learning audit event kind: {kind}"
            )
        object.__setattr__(self, "kind", kind)

        for field_name in (
            "subject_digest",
            "policy_digest",
            "evidence_root",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )

        if self.parent_event_id is not None:
            object.__setattr__(
                self,
                "parent_event_id",
                _text(
                    "parent_event_id",
                    self.parent_event_id,
                ),
            )
            if self.parent_event_id == self.event_id:
                raise LearningAuditError(
                    "audit event cannot parent itself"
                )

        raw_details = dict(self.details)
        if len(raw_details) > 64:
            raise LearningAuditError(
                "details contains too many fields"
            )
        _stable_json(raw_details)
        object.__setattr__(
            self,
            "details",
            _freeze_json(raw_details),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.learning_audit_event.v2",
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
            "details": _thaw_json(self.details),
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
    policy_digest: str | None = None
    evidence_root: str | None = None
    decision: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "event_id",
            _text("event_id", self.event_id),
        )
        object.__setattr__(
            self,
            "event_digest",
            _sha("event_digest", self.event_digest),
        )
        for field_name in (
            "previous_root",
            "root_hash",
            "subject_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "kind",
            _text("kind", self.kind),
        )
        object.__setattr__(
            self,
            "subject_id",
            _text("subject_id", self.subject_id),
        )
        object.__setattr__(
            self,
            "sequence",
            _positive_int("sequence", self.sequence),
        )
        if self.policy_digest is not None:
            object.__setattr__(
                self,
                "policy_digest",
                _sha("policy_digest", self.policy_digest),
            )
        if self.evidence_root is not None:
            object.__setattr__(
                self,
                "evidence_root",
                _sha("evidence_root", self.evidence_root),
            )
        if self.decision is not None:
            object.__setattr__(
                self,
                "decision",
                _text("decision", self.decision),
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.learning_audit_receipt.v2",
            "event_id": self.event_id,
            "event_digest": self.event_digest,
            "sequence": self.sequence,
            "previous_root": self.previous_root,
            "root_hash": self.root_hash,
            "kind": self.kind,
            "subject_id": self.subject_id,
            "subject_digest": self.subject_digest,
            "policy_digest": self.policy_digest,
            "evidence_root": self.evidence_root,
            "decision": self.decision,
        }

    @property
    def receipt_digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class LearningAuditSnapshot:
    namespace: str
    length: int
    root_hash: str
    event_ids: tuple[str, ...]
    event_digests: tuple[str, ...]
    node_hashes: tuple[str, ...]
    snapshot_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "namespace",
            _text("namespace", self.namespace, maximum=128),
        )
        object.__setattr__(
            self,
            "length",
            _positive_int("length", self.length)
            if self.length
            else 0,
        )
        object.__setattr__(
            self,
            "root_hash",
            _sha("root_hash", self.root_hash),
        )
        ids = tuple(
            _text("event_id", item)
            for item in self.event_ids
        )
        digests = tuple(
            _sha("event_digest", item)
            for item in self.event_digests
        )
        nodes = tuple(
            _sha("node_hash", item)
            for item in self.node_hashes
        )
        if not (
            len(ids)
            == len(digests)
            == len(nodes)
            == self.length
        ):
            raise LearningAuditError(
                "audit snapshot arrays must match snapshot length"
            )
        if len(ids) != len(set(ids)):
            raise LearningAuditError(
                "audit snapshot event ids must be unique"
            )
        object.__setattr__(self, "event_ids", ids)
        object.__setattr__(self, "event_digests", digests)
        object.__setattr__(self, "node_hashes", nodes)
        object.__setattr__(
            self,
            "snapshot_digest",
            _sha("snapshot_digest", self.snapshot_digest),
        )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.learning_audit_snapshot.v1",
            "namespace": self.namespace,
            "length": self.length,
            "root_hash": self.root_hash,
            "event_ids": list(self.event_ids),
            "event_digests": list(self.event_digests),
            "node_hashes": list(self.node_hashes),
        }

    def verify_identity(self) -> bool:
        return self.snapshot_digest == _digest(self.payload())


class LearningAuditLedger:
    """Typed learned-model lifecycle ledger over the evidence chain."""

    def __init__(
        self,
        backend: EvidenceStateBackend,
        *,
        namespace: str = "ai-learning-audit-v1",
        max_events: int = 1_000_000,
    ) -> None:
        self._namespace = _text(
            "namespace",
            namespace,
            maximum=128,
        )
        self._chain = ContentAddressedEvidenceChain(
            backend,
            namespace=self._namespace,
            max_events=max_events,
        )
        self._lock = threading.RLock()

    @staticmethod
    def _event_from_node(node: EvidenceNode) -> LearningAuditEvent:
        payload = dict(node.payload)
        try:
            return LearningAuditEvent(
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
        except (
            KeyError,
            LearningAuditError,
            TypeError,
        ) as exc:
            raise LearningAuditError(
                "stored audit node cannot be reconstructed"
            ) from exc

    def append(
        self,
        event: LearningAuditEvent,
    ) -> LearningAuditReceipt:
        if not isinstance(event, LearningAuditEvent):
            raise TypeError(
                "event must be LearningAuditEvent"
            )
        with self._lock:
            committed = self._chain.snapshot()
            by_id: dict[str, LearningAuditEvent] = {}
            for node in committed:
                stored = self._event_from_node(node)
                if stored.event_id in by_id:
                    raise LearningAuditError(
                        "stored audit chain contains duplicate event id"
                    )
                by_id[stored.event_id] = stored

            if event.event_id in by_id:
                raise LearningAuditError(
                    "event_id is already committed"
                )
            if event.parent_event_id is not None:
                parent = by_id.get(event.parent_event_id)
                if parent is None:
                    raise LearningAuditError(
                        "parent_event_id is not committed"
                    )
                if parent.subject_id != event.subject_id:
                    raise LearningAuditError(
                        "parent audit event crosses subject boundary"
                    )

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
                policy_digest=event.policy_digest,
                evidence_root=event.evidence_root,
                decision=event.decision,
            )

    def verify(self) -> bool:
        with self._lock:
            if not self._chain.verify():
                return False
            seen: dict[str, LearningAuditEvent] = {}
            for node in self._chain.snapshot():
                try:
                    event = self._event_from_node(node)
                except LearningAuditError:
                    return False
                payload = dict(node.payload)
                if payload.get("event_digest") != event.event_digest:
                    return False
                if event.event_id in seen:
                    return False
                if event.parent_event_id is not None:
                    parent = seen.get(event.parent_event_id)
                    if parent is None:
                        return False
                    if parent.subject_id != event.subject_id:
                        return False
                seen[event.event_id] = event
            return True

    def verify_receipt(
        self,
        receipt: LearningAuditReceipt,
    ) -> bool:
        if not isinstance(receipt, LearningAuditReceipt):
            raise TypeError(
                "receipt must be LearningAuditReceipt"
            )
        with self._lock:
            try:
                node = self._chain.get_node(receipt.root_hash)
            except (EvidenceCorruption, ValueError):
                return False
            payload = dict(node.payload)
            try:
                event = self._event_from_node(node)
            except LearningAuditError:
                return False
            return (
                node.sequence == receipt.sequence
                and node.previous_hash == receipt.previous_root
                and node.kind == receipt.kind
                and event.event_id == receipt.event_id
                and event.event_digest == receipt.event_digest
                and event.subject_id == receipt.subject_id
                and event.subject_digest == receipt.subject_digest
                and (
                    receipt.policy_digest is None
                    or event.policy_digest == receipt.policy_digest
                )
                and (
                    receipt.evidence_root is None
                    or event.evidence_root == receipt.evidence_root
                )
                and (
                    receipt.decision is None
                    or event.decision == receipt.decision
                )
                and payload.get("event_digest") == event.event_digest
                and self._chain.verify_root(receipt.root_hash)
            )

    def snapshot_receipt(self) -> LearningAuditSnapshot:
        with self._lock:
            nodes = self._chain.snapshot()
            ids: list[str] = []
            digests: list[str] = []
            hashes: list[str] = []
            for node in nodes:
                event = self._event_from_node(node)
                ids.append(event.event_id)
                digests.append(event.event_digest)
                hashes.append(node.node_hash)
            payload = {
                "schema_version": "skeleton.learning_audit_snapshot.v1",
                "namespace": self._namespace,
                "length": len(nodes),
                "root_hash": self._chain.root_hash(),
                "event_ids": ids,
                "event_digests": digests,
                "node_hashes": hashes,
            }
            return LearningAuditSnapshot(
                namespace=self._namespace,
                length=len(nodes),
                root_hash=payload["root_hash"],
                event_ids=tuple(ids),
                event_digests=tuple(digests),
                node_hashes=tuple(hashes),
                snapshot_digest=_digest(payload),
            )

    def verify_snapshot(
        self,
        snapshot: LearningAuditSnapshot,
    ) -> bool:
        if not isinstance(snapshot, LearningAuditSnapshot):
            raise TypeError(
                "snapshot must be LearningAuditSnapshot"
            )
        if snapshot.namespace != self._namespace:
            return False
        if not snapshot.verify_identity():
            return False
        current = self.snapshot_receipt()
        return current == snapshot and self.verify()

    def root_hash(self) -> str:
        with self._lock:
            return self._chain.root_hash()

    def length(self) -> int:
        with self._lock:
            return self._chain.length()

    def snapshot(self) -> tuple[EvidenceNode, ...]:
        with self._lock:
            return self._chain.snapshot()


__all__ = [
    "EVENT_KINDS",
    "LearningAuditError",
    "LearningAuditEvent",
    "LearningAuditLedger",
    "LearningAuditReceipt",
    "LearningAuditSnapshot",
]
