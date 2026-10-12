"""Compatibility shim — re-exports `skeleton.shells.ai.audit_anchor`.

This shim exists so callers of `skeleton.ai.shell.audit_anchor` keep working while `skeleton.shells.ai.audit_anchor` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.audit_anchor import (
    AIAuditAnchor,
    SignedAIAuditAnchor,
    AIAuditAnchorStore,
)

__all__ = ['AIAuditAnchor', 'SignedAIAuditAnchor', 'AIAuditAnchorStore']
