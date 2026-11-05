"""Authenticated offline request envelopes; replay prevention is separate.

An HMAC is a shared-key authenticity check, not a signature or proof of
entitlement. The key must be issued through an operator-controlled channel.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import hmac

from .contracts import canonical_bytes, strict_integer
from .errors import deny
from .identities import Scope, require_id
from .model_pins import require_sha256

MAX_TTL_MS = 300000


def _require_key(key: bytes) -> bytes:
    if type(key) is not bytes or not 32 <= len(key) <= 4096:
        deny("envelope-key")
    return key


@dataclass(frozen=True, slots=True)
class SignedEnvelope:
    scope_key: str
    nonce: str
    sequence: int
    payload_sha256: str
    issued_ms: int
    expires_ms: int
    mac_sha256: str

    def _payload(self) -> dict:
        return {
            "schema": "skeleton.ai.native-envelope.v1",
            "scope": self.scope_key,
            "nonce": self.nonce,
            "sequence": self.sequence,
            "payload_sha256": self.payload_sha256,
            "issued_ms": self.issued_ms,
            "expires_ms": self.expires_ms,
        }

    @classmethod
    def sign(
        cls,
        key: bytes,
        *,
        scope: Scope,
        nonce: str,
        sequence: int,
        payload_sha256: str,
        issued_ms: int,
        expires_ms: int,
    ) -> "SignedEnvelope":
        _require_key(key)
        if type(scope) is not Scope:
            deny("envelope-scope")
        require_id(nonce, "nonce")
        strict_integer(sequence, minimum=1, maximum=2**63 - 1, field="sequence")
        require_sha256(payload_sha256)
        strict_integer(issued_ms, minimum=0, maximum=2**63 - 1, field="issued")
        strict_integer(expires_ms, minimum=0, maximum=2**63 - 1, field="expires")
        if not 0 < expires_ms - issued_ms <= MAX_TTL_MS:
            deny("envelope-ttl")
        unsigned = cls(
            scope.key, nonce, sequence, payload_sha256,
            issued_ms, expires_ms, "0" * 64,
        )
        mac = hmac.new(key, canonical_bytes(unsigned._payload()), hashlib.sha256).hexdigest()
        return replace(unsigned, mac_sha256=mac)

    def verify(
        self,
        key: bytes,
        *,
        scope: Scope,
        payload_sha256: str,
        now_ms: int,
    ) -> None:
        _require_key(key)
        if type(scope) is not Scope or scope.key != self.scope_key:
            deny("envelope-scope")
        require_sha256(payload_sha256)
        if not hmac.compare_digest(self.payload_sha256, payload_sha256):
            deny("envelope-payload")
        strict_integer(now_ms, minimum=0, maximum=2**63 - 1, field="clock")
        if now_ms < self.issued_ms or now_ms >= self.expires_ms:
            deny("envelope-expired")
        require_sha256(self.mac_sha256)
        proof = hmac.new(key, canonical_bytes(self._payload()), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(proof, self.mac_sha256):
            deny("envelope-mac")
