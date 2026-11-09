"""Canonical deterministic verification primitives.

This package contains reusable claim identity and citation integrity logic.
Backend modules remain compatibility facades so verification semantics have one
implementation authority.
"""

from .claim_identity import (
    ClaimFingerprint,
    ClaimIdentityEngine,
    ClaimMatch,
    fingerprint_claim,
)
from .citation_integrity import (
    CitationBinding,
    CitationIntegrityEngine,
    CitationIntegrityReport,
)

__all__ = [
    "ClaimFingerprint",
    "ClaimIdentityEngine",
    "ClaimMatch",
    "fingerprint_claim",
    "CitationBinding",
    "CitationIntegrityEngine",
    "CitationIntegrityReport",
]
