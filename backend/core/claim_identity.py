"""Compatibility facade for canonical claim identity primitives."""

from skeleton.verification.claim_identity import (
    ClaimFingerprint,
    ClaimIdentityEngine,
    ClaimMatch,
    _NEGATION,
    _RELATION_PATTERNS,
    _STOP,
    _UNIT_ALIASES,
    _canonical,
    _clean,
    _jaccard,
    _relation,
    _sha,
    _stem,
    fingerprint_claim,
)

__all__ = [
    "ClaimFingerprint",
    "ClaimIdentityEngine",
    "ClaimMatch",
    "fingerprint_claim",
]
