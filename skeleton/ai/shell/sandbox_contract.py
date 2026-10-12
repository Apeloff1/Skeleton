"""Compatibility shim — re-exports `skeleton.shells.ai.sandbox_contract`.

This shim exists so callers of `skeleton.ai.shell.sandbox_contract` keep working while `skeleton.shells.ai.sandbox_contract` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.sandbox_contract import (
    AISandboxContract,
    AISandboxContractBuilder,
)

__all__ = ['AISandboxContract', 'AISandboxContractBuilder']
