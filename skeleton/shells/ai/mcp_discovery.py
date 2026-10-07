"""Principal-filtered deterministic MCP tool discovery."""

from __future__ import annotations

import hashlib
import json

from skeleton.shells.ai.mcp import MCPToolList, MCPToolSurface
from skeleton.shells.ai.mcp_authz import MCPAuthorization


class MCPPrincipalDiscovery:
    def __init__(
        self,
        surface: MCPToolSurface,
        authorization: MCPAuthorization,
    ) -> None:
        self.surface = surface
        self.authorization = authorization

    def list_tools(self, principal: str) -> MCPToolList:
        base = self.surface.list_tools()
        tools = tuple(
            tool
            for tool in base.tools
            if self.authorization.inspect(principal, tool.name).allowed
        )
        raw = json.dumps(
            [item.to_dict() for item in tools],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        principal_binding = hashlib.sha256(principal.encode()).hexdigest()
        digest = hashlib.sha256(
            raw + b":" + principal_binding.encode()
        ).hexdigest()
        return MCPToolList(
            base.protocol_revision,
            tools,
            base.ttl_ms,
            "private",
            digest,
        )
