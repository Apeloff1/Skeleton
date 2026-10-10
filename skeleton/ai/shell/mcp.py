"""Compatibility shim — re-exports `skeleton.shells.ai.mcp`.

This shim exists so callers of `skeleton.ai.shell.mcp` keep working while `skeleton.shells.ai.mcp` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.mcp import (
    MCP_PROTOCOL_REVISION,
    MCPToolDescriptor,
    MCPToolList,
    MCPRequestEnvelope,
    MCPResponseEnvelope,
    MCPToolSurface,
)

__all__ = ['MCP_PROTOCOL_REVISION', 'MCPToolDescriptor', 'MCPToolList', 'MCPRequestEnvelope', 'MCPResponseEnvelope', 'MCPToolSurface']
