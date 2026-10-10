"""Compatibility shim — re-exports `skeleton.shells.ai.model_port`.

This shim exists so callers of `skeleton.ai.shell.model_port` keep working while `skeleton.shells.ai.model_port` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.model_port import (
    ModelPrivacyBoundary,
    ModelCapabilities,
    AIModelPort,
    CallableAIModelPort,
)

__all__ = ['ModelPrivacyBoundary', 'ModelCapabilities', 'AIModelPort', 'CallableAIModelPort']
