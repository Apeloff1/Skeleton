"""Compatibility shim — re-exports `skeleton.shells.ai.approval`.

This shim exists so callers of `skeleton.ai.shell.approval` keep working while `skeleton.shells.ai.approval` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.approval import (
    AIPlanApproval,
    AIApprovalError,
    AIApprovalRegistry,
)

__all__ = ['AIPlanApproval', 'AIApprovalError', 'AIApprovalRegistry']
