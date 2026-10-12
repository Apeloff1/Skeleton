"""Compatibility shim — re-exports `skeleton.shells.ai.effects`.

This shim exists so callers of `skeleton.ai.shell.effects` keep working while `skeleton.shells.ai.effects` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.effects import (
    EffectKind,
    EffectContract,
    EffectRegistry,
)

__all__ = ['EffectKind', 'EffectContract', 'EffectRegistry']
