"""In-court helper: require Keyholder-signed attestation (AUDIT F4).

Diplomat-style propose paths that bypass Gate HMAC must call this before
accepting an attester identity. Bare self-declared attester strings are
rejected — only a verified envelope yields an attester public id.
"""

from __future__ import annotations

from typing import Any, Collection, Mapping, Optional, Union

from skeleton.kernel.attest import AttestError, verify_envelope
from skeleton.kernel.keyholder import Keyholder


def require_signed_attest(
    envelope: Union[Mapping[str, Any], str, None],
    *,
    trusted_publics: Optional[Collection[str]] = None,
    keyholder: Optional[Keyholder] = None,
    now: Optional[float] = None,
) -> str:
    """Return verified ``attester_public`` or raise ``AttestError``.

    Accepts only a signed envelope mapping. A bare attester string (the
    legacy diplomat ``gf_propose(..., attester, ...)`` shape) is rejected
    so callers cannot skip Keyholder-backed attestation.
    """
    if envelope is None:
        raise AttestError("unsigned attestation: envelope required")
    if isinstance(envelope, str):
        raise AttestError(
            "bare attester string rejected; signed attestation envelope required"
        )
    if not isinstance(envelope, Mapping):
        raise AttestError("attestation envelope must be a mapping")
    if not envelope:
        raise AttestError("unsigned attestation: empty envelope")

    # Explicit empty-attester guard for partial dicts before verify_envelope.
    attester = envelope.get("attester_public")
    if attester is not None and not str(attester).strip():
        raise AttestError("empty attester_public")

    return verify_envelope(
        envelope,
        trusted_publics=trusted_publics,
        keyholder=keyholder,
        now=now,
    )
