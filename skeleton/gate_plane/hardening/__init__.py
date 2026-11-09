"""Pack F hardening for the s2s plane.

* :mod:`.request_id` — request-id / W3C trace / hop propagation across HTTP
  and bus hops, with loop detection.
* :mod:`.claims` — stricter claim policy on verified tokens (kid pinning,
  scope ceilings, freshness, ext claims, cnf / rid binding).
* :mod:`.mutual` — mTLS-style mutual auth (ASGI TLS ext / trusted XFCC,
  SPIFFE identities) and HMAC signed requests.
* :mod:`.ratelimit` — GCRA rate limits per verified service identity.
* :mod:`.gate` — :class:`HardenedS2SGate` / ASGI middleware composing all
  of the above on top of the existing ``S2SAuthGate``.

Opt-in library code; no edits to ``skeleton/api/server.py``.
"""

from __future__ import annotations

from skeleton.gate_plane.hardening.claims import (
    CNF_CLAIM,
    RID_CLAIM,
    ClaimsPolicy,
    HardenedVerifier,
    HardeningCode,
    HardeningError,
    VerificationScope,
    bound_extra,
    normalize_thumbprint,
    thumbprint_b64url,
    verification_scope,
)
from skeleton.gate_plane.hardening.gate import (
    HARDENED_GATE_LAYER,
    HardenedDecision,
    HardenedOutcome,
    HardenedS2SGate,
    HardenedS2SMiddleware,
    SignatureMode,
    build_hardened_gate,
    install_hardened_gate,
)
from skeleton.gate_plane.hardening.mutual import (
    MutualAuthCode,
    MutualAuthMode,
    MutualAuthPolicy,
    NonceCache,
    PeerCertificate,
    PeerExtractor,
    PeerResult,
    RequestSigner,
    RequestVerifier,
    SpiffeMap,
    parse_xfcc,
    thumbprint_from_der,
)
from skeleton.gate_plane.hardening.ratelimit import RateDecision, RateRule, ServiceRateLimiter, limiter_from_config
from skeleton.gate_plane.hardening.request_id import (
    HopLimitExceeded,
    PropagationPolicy,
    RequestContext,
    RequestIdStage,
    TraceParent,
    bind_context,
    current_context,
    envelope_headers,
    extract_context,
    propagate,
)

__all__ = [
    "CNF_CLAIM",
    "ClaimsPolicy",
    "HARDENED_GATE_LAYER",
    "HardenedDecision",
    "HardenedOutcome",
    "HardenedS2SGate",
    "HardenedS2SMiddleware",
    "HardenedVerifier",
    "HardeningCode",
    "HardeningError",
    "HopLimitExceeded",
    "MutualAuthCode",
    "MutualAuthMode",
    "MutualAuthPolicy",
    "NonceCache",
    "PeerCertificate",
    "PeerExtractor",
    "PeerResult",
    "PropagationPolicy",
    "RID_CLAIM",
    "RateDecision",
    "RateRule",
    "RequestContext",
    "RequestIdStage",
    "RequestSigner",
    "RequestVerifier",
    "ServiceRateLimiter",
    "SignatureMode",
    "SpiffeMap",
    "TraceParent",
    "VerificationScope",
    "bind_context",
    "bound_extra",
    "build_hardened_gate",
    "current_context",
    "envelope_headers",
    "extract_context",
    "install_hardened_gate",
    "limiter_from_config",
    "normalize_thumbprint",
    "parse_xfcc",
    "propagate",
    "thumbprint_b64url",
    "thumbprint_from_der",
    "verification_scope",
]
