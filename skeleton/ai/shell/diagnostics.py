"""Compatibility shim — re-exports `skeleton.shells.ai.diagnostics`.

This shim exists so callers of `skeleton.ai.shell.diagnostics` keep working while `skeleton.shells.ai.diagnostics` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.diagnostics import (
    AIDiagnosticSeverity,
    AIDiagnosticFinding,
    AIDiagnosticsReport,
    AIShellDiagnostics,
)

__all__ = ['AIDiagnosticSeverity', 'AIDiagnosticFinding', 'AIDiagnosticsReport', 'AIShellDiagnostics']
