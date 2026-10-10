"""Compatibility shim — re-exports `skeleton.shells.ai.router`.

This shim exists so callers of `skeleton.ai.shell.router` keep working while `skeleton.shells.ai.router` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.router import (
    RoutedTool,
    AIToolRouter,
)

__all__ = ['RoutedTool', 'AIToolRouter']
