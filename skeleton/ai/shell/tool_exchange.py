"""Compatibility shim — re-exports `skeleton.shells.ai.tool_exchange`.

This shim exists so callers of `skeleton.ai.shell.tool_exchange` keep working while `skeleton.shells.ai.tool_exchange` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.tool_exchange import (
    AIToolCall,
    AIToolResult,
)

__all__ = ['AIToolCall', 'AIToolResult']
