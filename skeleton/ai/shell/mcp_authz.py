"""Compatibility shim — re-exports `skeleton.shells.ai.mcp_authz`.

This shim exists so callers of `skeleton.ai.shell.mcp_authz` keep working while `skeleton.shells.ai.mcp_authz` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.mcp_authz import (
    MCPPrincipalPolicy,
    MCPAuthorizationDecision,
    MCPAuthorization,
)

__all__ = ['MCPPrincipalPolicy', 'MCPAuthorizationDecision', 'MCPAuthorization']
