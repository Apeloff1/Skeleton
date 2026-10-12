"""Compatibility shim — re-exports `skeleton.shells.ai.catalog`.

This shim exists so callers of `skeleton.ai.shell.catalog` keep working while `skeleton.shells.ai.catalog` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.catalog import (
    AIToolCard,
    AIToolCatalog,
)

__all__ = ['AIToolCard', 'AIToolCatalog']
