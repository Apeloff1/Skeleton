"""Explicit operator-authorized reconciliation of a committed offline inference lease.

A recovery grant is scoped to one authenticated custody generation and one
pending lease. It never authorizes a backend retry, model execution, hardware
qualification, or rollback-anchor repair. The recovery key is independently
provisioned by the trusted application and never stored in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from typing import Mapping

SCHEMA = "skeleton.ai.fair-stream-recovery-authorization.v1"
MAX_GRANT_BYTES = 1024


class RecoveryAuthorizationDenied(RuntimeError):
    """A scoped, independently authenticated operator approval is missing."""


def _hex(value: object, length: int, label: str) -> str:
    if type(value) is not str or len(value) != length or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise RecoveryAuthorizationDenied("invalid " + label)
    return value


def _key(value: object) -> bytes:
    if type(value) is not bytes or not 32 <= len(value) <= 128:
        raise RecoveryAuthorizationDenied("independent recovery key required")
    return value


def _body(
    *, session_id: str, generation: int, checkpoint_digest: str,
    lease_id: str, nonce: str,
) -> dict[str, object]:
    _hex(session_id, 32, "session")
    _hex(checkpoint_digest, 64, "checkpoint")
    _hex(lease_id, 64, "lease")
    _hex(nonce, 32, "operator nonce")
    if type(generation) is not int or not 0 <= generation < (1 << 63):
        raise RecoveryAuthorizationDenied("invalid custody generation")
    return {
        "schema": SCHEMA,
        "session_id": session_id,
        "generation": generation,
        "checkpoint_digest": checkpoint_digest,
        "lease_id": lease_id,
        "nonce": nonce,
    }


def _encoded(body: Mapping[str, object]) -> bytes:
    try:
        encoded = json.dumps(
            body, sort_keys=True, separators=(",", ":"),
            allow_nan=False, ensure_ascii=True,
        ).encode("ascii")
    except (ValueError, TypeError, OverflowError) as exc:
        raise RecoveryAuthorizationDenied("invalid recovery grant encoding") from exc
    if len(encoded) > MAX_GRANT_BYTES:
        raise RecoveryAuthorizationDenied("recovery grant exceeds byte budget")
    return encoded


@dataclass(frozen=True, slots=True)
class RecoveryAuthorization:
    """Opaque signed approval; nonce must originate from a trusted operator."""

    session_id: str
    generation: int
    checkpoint_digest: str
    lease_id: str
    nonce: str
    mac: str

    def __post_init__(self) -> None:
        _body(
            session_id=self.session_id, generation=self.generation,
            checkpoint_digest=self.checkpoint_digest,
            lease_id=self.lease_id, nonce=self.nonce,
        )
        _hex(self.mac, 64, "grant MAC")


def issue_recovery_authorization(
    *, recovery_key: bytes, session_id: str, generation: int,
    checkpoint_digest: str, lease_id: str, nonce: str,
) -> RecoveryAuthorization:
    """Trusted operator-side signer; NEVER expose as an unguarded API route."""
    body = _body(
        session_id=session_id, generation=generation,
        checkpoint_digest=checkpoint_digest, lease_id=lease_id, nonce=nonce,
    )
    mac = hmac.new(_key(recovery_key), _encoded(body), sha256).hexdigest()
    return RecoveryAuthorization(
        session_id, generation, checkpoint_digest, lease_id, nonce, mac,
    )


def verify_recovery_authorization(
    approval: RecoveryAuthorization, *, recovery_key: bytes,
    state: Mapping[str, object], lease_id: str,
) -> None:
    """Check exact current signed custody identity before any journal read.

    The caller must separately validate the custody high-watermark and the
    journal's committed execution receipt. An approval is NOT an execution
    receipt and cannot retire a lease on its own.
    """
    if type(approval) is not RecoveryAuthorization:
        raise RecoveryAuthorizationDenied("canonical operator approval required")
    if not isinstance(state, Mapping):
        raise RecoveryAuthorizationDenied("verified custody state required")
    body = _body(
        session_id=approval.session_id, generation=approval.generation,
        checkpoint_digest=approval.checkpoint_digest,
        lease_id=approval.lease_id, nonce=approval.nonce,
    )
    if (
        approval.session_id != state.get("session_id")
        or approval.generation != state.get("generation")
        or approval.checkpoint_digest != state.get("checkpoint_digest")
        or approval.lease_id != lease_id
    ):
        raise RecoveryAuthorizationDenied("operator approval does not bind current lease")
    expected = hmac.new(_key(recovery_key), _encoded(body), sha256).hexdigest()
    if not hmac.compare_digest(expected, approval.mac):
        raise RecoveryAuthorizationDenied("operator approval authentication failed")


__all__ = [
    "RecoveryAuthorization", "RecoveryAuthorizationDenied",
    "issue_recovery_authorization", "verify_recovery_authorization",
]
