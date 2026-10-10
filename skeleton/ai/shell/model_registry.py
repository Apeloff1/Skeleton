"""Compatibility shim — re-exports `skeleton.shells.ai.model_registry`.

This shim exists so callers of `skeleton.ai.shell.model_registry` keep working while `skeleton.shells.ai.model_registry` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.model_registry import (
    RegisteredModel,
    ModelRegistryConflict,
    AIModelRegistry,
)

__all__ = ['RegisteredModel', 'ModelRegistryConflict', 'AIModelRegistry']
