"""Compatibility shim — re-exports `skeleton.shells.ai.audit_export`.

This shim exists so callers of `skeleton.ai.shell.audit_export` keep working while `skeleton.shells.ai.audit_export` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.audit_export import (
    AIAuditExport,
    AIAuditExporter,
)

__all__ = ['AIAuditExport', 'AIAuditExporter']
