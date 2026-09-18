"""Stateless gateway from MCP-style requests into AI shell review inputs.

The gateway validates protocol and authorization. It does not execute tools.
"""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.mcp import MCPRequestEnvelope, MCPResponseEnvelope, MCPToolSurface
from skeleton.shells.ai.mcp_authz import MCPAuthorization
from skeleton.shells.ai.mcp_replay import MCPReplayGuard
from skeleton.shells.ai.types import AIAction


@dataclass(frozen=True)
class MCPPreparedToolCall:
    request: MCPRequestEnvelope
    principal: str
    action: AIAction

    def to_dict(self) -> dict[str, object]:
        return {
            "request": self.request.to_dict(),
            "principal": self.principal,
            "action": self.action.to_dict(),
        }


class MCPAIShellGateway:
    def __init__(
        self,
        tools: MCPToolSurface,
        authorization: MCPAuthorization,
        *,
        replay_guard: MCPReplayGuard | None = None,
    ) -> None:
        self.tools = tools
        self.authorization = authorization
        self.replay_guard = replay_guard

    def list_tools(self) -> MCPResponseEnvelope:
        listing = self.tools.list_tools()
        return MCPResponseEnvelope(
            "tools-list",
            True,
            listing.to_dict(),
        )

    def prepare_call(
        self,
        request: MCPRequestEnvelope,
        *,
        principal: str,
    ) -> MCPPreparedToolCall:
        if request.protocol_revision != self.tools.list_tools().protocol_revision:
            raise ValueError("unsupported MCP protocol revision")
        if request.method != "tools/call":
            raise ValueError("MCP AI shell gateway accepts only tools/call")
        names = {item.name for item in self.tools.descriptors()}
        if request.name not in names:
            raise KeyError(request.name)
        args = request.arguments
        raw_args = args.get("args", [])
        if not isinstance(raw_args, list):
            raise ValueError("MCP tool args must be a list")
        environment = args.get("environmentRefs", {})
        if not isinstance(environment, dict):
            raise ValueError("MCP environmentRefs must be an object")
        timeout = args.get("timeoutSeconds")
        if timeout is not None:
            timeout = float(timeout)
        self.authorization.require(
            principal,
            request.name,
            timeout_seconds=timeout,
        )
        action = AIAction(
            action_id=request.request_id,
            command=request.name,
            args=tuple(raw_args),
            cwd=args.get("cwd"),
            environment_refs=environment,
            timeout_seconds=timeout,
            purpose=str(args.get("purpose", "")),
        )
        if self.replay_guard is not None:
            self.replay_guard.admit(
                request,
                principal=principal,
            )
        return MCPPreparedToolCall(request, principal, action)
