"""Signed execution seals binding reviewed AI authority to exact state."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
import time
from typing import Callable

from skeleton.shells.ai.stale_guard import PlanPin


@dataclass(frozen=True)
class ExecutionSeal:
    seal_id: str
    principal: str
    session_id: str
    plan_pin: PlanPin
    preconditions_digest: str
    approval_id: str
    issued_at: float
    expires_at: float
    nonce: str
    signature: str

    def __post_init__(self) -> None:
        if not self.seal_id or len(self.seal_id) > 128:
            raise ValueError("invalid execution seal_id")
        if not self.principal or not self.session_id:
            raise ValueError("execution seal identity fields required")
        if self.preconditions_digest and len(self.preconditions_digest) != 64:
            raise ValueError("preconditions_digest must be SHA-256 hex")
        if self.expires_at <= self.issued_at:
            raise ValueError("execution seal expiry must follow issue time")
        if len(self.signature) != 64:
            raise ValueError("execution seal signature must be SHA-256 HMAC")

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "seal_id": self.seal_id,
            "principal": self.principal,
            "session_id": self.session_id,
            "plan_pin": self.plan_pin.to_dict(),
            "preconditions_digest": self.preconditions_digest,
            "approval_id": self.approval_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }

    def to_dict(self) -> dict[str, object]:
        data = self.unsigned_dict()
        data["signature"] = self.signature
        return data


class ExecutionSealError(RuntimeError):
    pass


class ExecutionSealAuthority:
    """HMAC signer for short-lived reviewed execution authority.

    The key remains local to trusted service code and must never be sent to a
    model, child process, audit event, or review UI.
    """

    def __init__(
        self,
        key: bytes,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("execution seal key must be at least 32 bytes")
        self._key = key
        self._clock = clock

    def _signature(self, payload: dict[str, object]) -> str:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hmac.new(self._key, raw, hashlib.sha256).hexdigest()

    def issue(
        self,
        *,
        principal: str,
        session_id: str,
        plan_pin: PlanPin,
        preconditions_digest: str = "",
        approval_id: str = "",
        ttl_seconds: float = 60.0,
    ) -> ExecutionSeal:
        if ttl_seconds <= 0:
            raise ValueError("execution seal TTL must be positive")
        now = self._clock()
        nonce = secrets.token_hex(16)
        seed = f"{principal}:{session_id}:{nonce}:{now}".encode()
        seal_id = hashlib.sha256(seed).hexdigest()[:32]
        unsigned = {
            "seal_id": seal_id,
            "principal": principal,
            "session_id": session_id,
            "plan_pin": plan_pin.to_dict(),
            "preconditions_digest": preconditions_digest,
            "approval_id": approval_id,
            "issued_at": now,
            "expires_at": now + ttl_seconds,
            "nonce": nonce,
        }
        return ExecutionSeal(
            seal_id,
            principal,
            session_id,
            plan_pin,
            preconditions_digest,
            approval_id,
            now,
            now + ttl_seconds,
            nonce,
            self._signature(unsigned),
        )

    def verify(
        self,
        seal: ExecutionSeal,
        *,
        principal: str,
        session_id: str,
        plan_pin: PlanPin,
        preconditions_digest: str = "",
        approval_id: str = "",
    ) -> None:
        if seal.expires_at <= self._clock():
            raise ExecutionSealError("execution seal expired")
        if seal.principal != principal:
            raise ExecutionSealError("execution seal principal mismatch")
        if seal.session_id != session_id:
            raise ExecutionSealError("execution seal session mismatch")
        if seal.plan_pin != plan_pin:
            raise ExecutionSealError("execution seal plan pin mismatch")
        if seal.preconditions_digest != preconditions_digest:
            raise ExecutionSealError("execution seal preconditions mismatch")
        if seal.approval_id != approval_id:
            raise ExecutionSealError("execution seal approval mismatch")
        expected = self._signature(seal.unsigned_dict())
        if not hmac.compare_digest(expected, seal.signature):
            raise ExecutionSealError("execution seal signature mismatch")
