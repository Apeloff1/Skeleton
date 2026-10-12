"""Compatibility shim — re-exports `skeleton.shells.ai.source_digest`.

This shim exists so callers of `skeleton.ai.shell.source_digest` keep working while `skeleton.shells.ai.source_digest` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.source_digest import (
    SourceDigestPolicy,
    SourceDigestError,
    SourceDigestProvider,
)

__all__ = ['SourceDigestPolicy', 'SourceDigestError', 'SourceDigestProvider']
