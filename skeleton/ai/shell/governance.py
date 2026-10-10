"""Compatibility shim — re-exports `skeleton.shells.ai.governance`.

This shim exists so callers of `skeleton.ai.shell.governance` keep working while `skeleton.shells.ai.governance` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.governance import (
    AIGovernanceSnapshot,
    AIShellGovernance,
)

__all__ = ['AIGovernanceSnapshot', 'AIShellGovernance']
