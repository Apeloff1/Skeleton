"""Compatibility shim — re-exports `skeleton.shells.ai.mcp_transport`.

This shim exists so callers of `skeleton.ai.shell.mcp_transport` keep working while `skeleton.shells.ai.mcp_transport` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.mcp_transport import (
    MCPTransportPolicy,
    MCPTransportDecision,
    MCPTransportValidator,
)

__all__ = ['MCPTransportPolicy', 'MCPTransportDecision', 'MCPTransportValidator']
