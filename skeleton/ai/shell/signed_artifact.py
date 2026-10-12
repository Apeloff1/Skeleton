"""Compatibility shim — re-exports `skeleton.shells.ai.signed_artifact`.

This shim exists so callers of `skeleton.ai.shell.signed_artifact` keep working while `skeleton.shells.ai.signed_artifact` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.signed_artifact import (
    SignedArtifact,
    ArtifactSignatureError,
    ArtifactSigner,
)

__all__ = ['SignedArtifact', 'ArtifactSignatureError', 'ArtifactSigner']
