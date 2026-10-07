"""Request seals — HMAC-SHA256 identity, verified, never self-declared.

The seal format is a treaty shared with the C# gate and the Rust spine:

    <principal>.<attester>.<expiry_epoch>.<sig>

where sig = hex(HMAC_SHA256(secret, "<principal>.<attester>.<expiry>")).
The same bytes verify on all three runtimes — a seal minted by the C# gate
is honored by the Rust courts and by this substrate without translation.

Fail-closed: without ZAIBATSU_SEAL_SECRET the verifier denies everything
and the minter refuses to issue. Constant-time compare throughout; expiry
is enforced against the clock, not the caller.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass

_ENV_SECRET = "ZAIBATSU_SEAL_SECRET"
_MAX_TTL_SECS = 3600


class SealError(Exception):
    """Any seal failure. Never carries distinguishing detail outward."""


def _secret() -> bytes:
    raw = os.environ.get(_ENV_SECRET, "")
    if not raw:
        raise SealError("seal secret not configured — the gate is closed")
    return raw.encode("utf-8")


@dataclass(frozen=True)
class Seal:
    principal: str
    attester: str
    expiry: int

    @property
    def payload(self) -> str:
        return f"{self.principal}.{self.attester}.{self.expiry}"


def mint(principal: str, attester: str, ttl_secs: int = 900) -> str:
    """Forge a seal. Callers must already hold operator authority."""
    if not principal or not attester or "." in principal or "." in attester:
        raise SealError("invalid seal fields")
    ttl = max(1, min(ttl_secs, _MAX_TTL_SECS))
    seal = Seal(principal, attester, int(time.time()) + ttl)
    sig = hmac.new(_secret(), seal.payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{seal.payload}.{sig}"


def verify(token: str, now: float | None = None) -> Seal:
    """Verify a seal or raise SealError. Identity comes only from here."""
    if not token or token.count(".") != 3:
        raise SealError("malformed seal")
    principal, attester, expiry_s, sig = token.split(".")
    try:
        expiry = int(expiry_s)
    except ValueError as exc:
        raise SealError("malformed seal") from exc
    seal = Seal(principal, attester, expiry)
    expected = hmac.new(_secret(), seal.payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise SealError("bad seal")
    if (now if now is not None else time.time()) > expiry:
        raise SealError("seal expired")
    return seal
