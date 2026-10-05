"""Diplomat-direct in-court attestation envelopes (AUDIT F4 remainder).

Gate HMAC (hmac_seal / PrincipalAuth) already closes auth at the HTTP edge.
Diplomat-direct consumers that bypass the Gate (e.g. ``gf_propose`` with a
bare self-declared ``attester`` string) still need a Keyholder-backed
signature over the proposal payload — verified **in-court**, not at Gate.

This module is that envelope + verify path. It reuses
``skeleton.kernel.keyholder`` (placeholder sha256 sign/verify matching
gameforge-rs ``keyholder.rs``). Do not invent a second crypto stack; when
real ed25519 lands in Keyholder, callers of this module stay unchanged.

Canonical payload (UTF-8, deterministic, trailing newline)::

    ATTEST-V1
    proposal_id:<utf-8 id>
    value_hash:<hex sha256 of value bytes>
    attester_public:<hex public id>
    expiry:<decimal unix seconds, or "-" if unset>

Signature = ``Keyholder.sign(canonical_bytes)`` (hex). Verification uses a
Keyholder whose ``public_hex`` matches ``attester_public`` (placeholder
crypto cannot verify against a bare public alone; real ed25519 will).
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Collection, Mapping, MutableMapping, Optional, Union

from skeleton.kernel.keyholder import Keyholder, get_keyholder

EnvelopeDict = MutableMapping[str, Any]
EnvelopeLike = Mapping[str, Any]


class AttestError(ValueError):
    """Raised when an attestation envelope is missing, expired, or invalid."""


def value_hash(value: Union[str, bytes]) -> str:
    """SHA-256 hex of proposal value bytes (UTF-8 if str)."""
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(
    *,
    proposal_id: str,
    value_hash: str,
    attester_public: str,
    expiry: Optional[int] = None,
) -> bytes:
    """Build the deterministic byte string that Keyholder signs/verifies."""
    exp = "-" if expiry is None else str(int(expiry))
    lines = (
        "ATTEST-V1",
        f"proposal_id:{proposal_id}",
        f"value_hash:{value_hash}",
        f"attester_public:{attester_public}",
        f"expiry:{exp}",
        "",
    )
    return "\n".join(lines).encode("utf-8")


def sign_envelope(
    *,
    proposal_id: str,
    value: Union[str, bytes],
    expiry: Optional[int] = None,
    keyholder: Optional[Keyholder] = None,
    include_value: bool = False,
) -> dict[str, Any]:
    """Sign a proposal attestation with the process Keyholder.

    Returns a plain dict suitable for JSON / diplomat consumers::

        proposal_id, value_hash, attester_public, signature [, expiry] [, value]
    """
    if not proposal_id:
        raise AttestError("proposal_id required")
    kh = keyholder if keyholder is not None else get_keyholder()
    vhash = value_hash(value)
    pub = kh.public_hex
    payload = canonical_bytes(
        proposal_id=proposal_id,
        value_hash=vhash,
        attester_public=pub,
        expiry=expiry,
    )
    env: dict[str, Any] = {
        "proposal_id": proposal_id,
        "value_hash": vhash,
        "attester_public": pub,
        "signature": kh.sign(payload),
    }
    if expiry is not None:
        env["expiry"] = int(expiry)
    if include_value:
        env["value"] = value.decode("utf-8") if isinstance(value, bytes) else value
    return env


def _field(envelope: EnvelopeLike, name: str) -> str:
    raw = envelope.get(name)
    if raw is None:
        raise AttestError(f"missing field: {name}")
    text = str(raw).strip()
    if not text:
        raise AttestError(f"empty field: {name}")
    return text


def verify_envelope(
    envelope: EnvelopeLike,
    *,
    trusted_publics: Optional[Collection[str]] = None,
    keyholder: Optional[Keyholder] = None,
    now: Optional[float] = None,
) -> str:
    """Verify a signed attestation envelope.

    Checks required fields, optional expiry, optional ``trusted_publics``
    allowlist, then Keyholder signature over the canonical payload.

    Returns the verified ``attester_public`` hex id.

    Raises:
        AttestError: on any validation or crypto failure.
    """
    if not isinstance(envelope, Mapping):
        raise AttestError("envelope must be a mapping")

    proposal_id = _field(envelope, "proposal_id")
    vhash = _field(envelope, "value_hash")
    attester_public = _field(envelope, "attester_public")
    signature = _field(envelope, "signature")

    expiry_raw = envelope.get("expiry")
    expiry: Optional[int]
    if expiry_raw is None or expiry_raw == "":
        expiry = None
    else:
        try:
            expiry = int(expiry_raw)
        except (TypeError, ValueError) as exc:
            raise AttestError("invalid expiry") from exc
        ts = time.time() if now is None else float(now)
        if expiry < ts:
            raise AttestError("attestation expired")

    if trusted_publics is not None and attester_public not in trusted_publics:
        raise AttestError("attester_public not in trusted_publics")

    kh = keyholder if keyholder is not None else get_keyholder()
    if kh.public_hex != attester_public:
        raise AttestError("attester_public does not match verifying keyholder")

    payload = canonical_bytes(
        proposal_id=proposal_id,
        value_hash=vhash,
        attester_public=attester_public,
        expiry=expiry,
    )
    if not kh.verify(payload, signature):
        raise AttestError("bad attestation signature")

    # If a concrete value was included, it must match value_hash.
    if "value" in envelope and envelope["value"] is not None:
        included = envelope["value"]
        if isinstance(included, bytes):
            got = value_hash(included)
        else:
            got = value_hash(str(included))
        if got != vhash:
            raise AttestError("value does not match value_hash")

    return attester_public
