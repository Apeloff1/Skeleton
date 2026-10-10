"""Compatibility shim — re-exports `skeleton.shells.ai.assurance_binding`.

This shim exists so callers of `skeleton.ai.shell.assurance_binding` keep working while `skeleton.shells.ai.assurance_binding` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.assurance_binding import (
    AssuranceBinding,
)

__all__ = ['AssuranceBinding']
