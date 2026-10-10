"""Compatibility shim — re-exports `skeleton.shells.ai.tool_guard`.

This shim exists so callers of `skeleton.ai.shell.tool_guard` keep working while `skeleton.shells.ai.tool_guard` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.tool_guard import (
    ToolGuardStage,
    ToolGuardDecision,
    ToolGuardTripwire,
    InputGuard,
    OutputGuard,
    AIToolGuardRegistry,
)

__all__ = ['ToolGuardStage', 'ToolGuardDecision', 'ToolGuardTripwire', 'InputGuard', 'OutputGuard', 'AIToolGuardRegistry']
