"""Compatibility facade for canonical citation integrity primitives."""

from skeleton.verification.citation_integrity import (
    CitationBinding,
    CitationIntegrityEngine,
    CitationIntegrityReport,
    _ALLOWED_BINDINGS,
    _EXTRACTIVE,
    _STRUCTURED,
    _canonical,
    _numbers,
    _overlap,
    _sha,
    _tokens,
)

__all__ = [
    "CitationBinding",
    "CitationIntegrityEngine",
    "CitationIntegrityReport",
]
