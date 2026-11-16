"""Single-use, action-scoped Ed25519 operator approval for canonical epochs.

The trusted application root pins the public key and expected deployment ID.
The operator signs external backup/quiescence/writer-inventory receipt digests;
this verifies their binding, not their physical truth. No signer or approval
is accepted from an HTTP request or model output. Process-local replay custody
is combined with the insert-only / terminal CAS authority in Mongo.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from threading import Lock
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_DOMAIN = b"skeleton.mongo.epoch-operator-approval.v1\x00"
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z", re.ASCII)
_DB = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}\Z", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MIGRATION = "quiescent-initial-epoch-v1"
_REVOCATION = "terminal-actor-revocation-v1"
_REASONS = frozenset(("operator-revoke", "security-incident", "authority-retired"))
_MAX_VALIDITY = 300


class EpochApprovalError(ValueError):
    """Malformed, expired, replayed or untrusted operator approval."""


def _identifier(value: object) -> bool:
    return type(value) is str and _ID.fullmatch(value) is not None


def _scope(value: object) -> bool:
    if (type(value) is not str or not 1 <= len(value) <= 512
            or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        return False
    try:
        return len(value.encode("utf-8", "strict")) <= 512
    except UnicodeError:
        return False


def _digest(value: object) -> bool:
    return type(value) is str and _HEX.fullmatch(value) is not None and value != "0" * 64


@dataclass(frozen=True, slots=True)
class EpochApproval:
    authority_id: str
    deployment_id: str
    approval_id: str
    database_name: str
    tenant_id: str
    actor_id: str
    purpose: str
    issued_at: int
    expires_at: int
    expected_epoch: int | None
    reason_code: str | None
    backup_sha256: str
    quiescence_sha256: str
    writer_inventory_sha256: str

    def __post_init__(self) -> None:
        if not all(_identifier(v) for v in (
                self.authority_id, self.deployment_id, self.approval_id)):
            raise EpochApprovalError("operator approval identity invalid")
        if type(self.database_name) is not str or _DB.fullmatch(self.database_name) is None:
            raise EpochApprovalError("operator approval database invalid")
        if not _scope(self.tenant_id) or not _scope(self.actor_id):
            raise EpochApprovalError("operator approval scope invalid")
        if (type(self.issued_at) is not int or type(self.expires_at) is not int
                or not 0 < self.issued_at < self.expires_at < (1 << 63)
                or self.expires_at - self.issued_at > _MAX_VALIDITY):
            raise EpochApprovalError("operator approval validity invalid")
        if not all(_digest(v) for v in (
                self.backup_sha256, self.quiescence_sha256, self.writer_inventory_sha256)):
            raise EpochApprovalError("operator evidence digest invalid")
        if type(self.purpose) is not str:
            raise EpochApprovalError("operator approval purpose invalid")
        if self.purpose == _MIGRATION:
            if self.expected_epoch is not None or self.reason_code is not None:
                raise EpochApprovalError("initial migration must not replace an epoch")
        elif self.purpose == _REVOCATION:
            if (type(self.expected_epoch) is not int or not 2 <= self.expected_epoch < (1 << 63) - 1
                    or self.expected_epoch % 2 or type(self.reason_code) is not str
                    or self.reason_code not in _REASONS):
                raise EpochApprovalError("terminal revocation binding invalid")
        else:
            raise EpochApprovalError("operator approval purpose invalid")

    def canonical_bytes(self) -> bytes:
        fields = {name: getattr(self, name) for name in self.__dataclass_fields__}
        raw = _DOMAIN + json.dumps(fields, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=True, allow_nan=False).encode("utf-8")
        if len(raw) > 8192:
            raise EpochApprovalError("operator approval exceeds bound")
        return raw


class EpochOperatorAuthorization:
    """One exact signed approval, pinned authority/deployment and action."""

    def __init__(self, *, approval: EpochApproval, signature: bytes,
                 authority_id: str, deployment_id: str, public_key: bytes) -> None:
        if (type(approval) is not EpochApproval or not _identifier(authority_id)
                or not _identifier(deployment_id) or approval.authority_id != authority_id
                or approval.deployment_id != deployment_id or type(public_key) is not bytes
                or len(public_key) != 32 or type(signature) is not bytes or len(signature) != 64):
            raise EpochApprovalError("operator approval trust anchor invalid")
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature, approval.canonical_bytes(),
            )
        except (InvalidSignature, ValueError, TypeError):
            raise EpochApprovalError("operator approval signature invalid") from None
        self._approval = approval
        self._signature = signature
        self._key = Ed25519PublicKey.from_public_bytes(public_key)
        self._lock = Lock()
        self._used = False

    async def __call__(self, **binding: Any) -> bool:
        approval = self._approval
        required = {
            "tenant_id": approval.tenant_id, "actor_id": approval.actor_id,
            "database_name": approval.database_name, "purpose": approval.purpose,
        }
        if approval.purpose == _REVOCATION:
            required.update(expected_epoch=approval.expected_epoch,
                            reason_code=approval.reason_code)
        if (set(binding) != set(required)
                or any(type(binding[k]) is not type(v) or binding[k] != v
                       for k, v in required.items())):
            return False
        # No await inside this critical section. Even competing tasks/threads
        # cannot consume one authorization twice in a running process.
        with self._lock:
            now = int(time.time())
            if self._used or not approval.issued_at <= now < approval.expires_at:
                return False
            try:
                self._key.verify(self._signature, approval.canonical_bytes())
            except (InvalidSignature, ValueError, TypeError):
                return False
            self._used = True
            return True


__all__ = ["EpochApproval", "EpochApprovalError", "EpochOperatorAuthorization"]
