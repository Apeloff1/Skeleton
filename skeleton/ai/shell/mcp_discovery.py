"""Compatibility shim — re-exports `skeleton.shells.ai.mcp_discovery`.

This shim exists so callers of `skeleton.ai.shell.mcp_discovery` keep working while `skeleton.shells.ai.mcp_discovery` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.mcp_discovery import (
    MCPPrincipalDiscovery,
)

__all__ = ['MCPPrincipalDiscovery']
