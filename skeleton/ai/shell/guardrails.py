"""Compatibility shim — re-exports `skeleton.shells.ai.guardrails`.

This shim exists so callers of `skeleton.ai.shell.guardrails` keep working while `skeleton.shells.ai.guardrails` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.guardrails import (
    GuardrailSeverity,
    GuardrailFinding,
    GuardrailReport,
    ModelOutputGuard,
)

__all__ = ['GuardrailSeverity', 'GuardrailFinding', 'GuardrailReport', 'ModelOutputGuard']
