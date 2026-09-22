"""Stateless MCP-2026-style export surface for AI shell tools.

This module is transport-agnostic. It emits deterministic tool descriptors,
self-describing request envelopes, routing headers, and cache hints while
leaving authorization and execution in the existing AI shell service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.ai.manifest import AIToolManifest

MCP_PROTOCOL_REVISION = "2026-07-28"


@dataclass(frozen=True)
class MCPToolDescriptor:
    name: str
    description: str
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]
    annotations: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 128:
            raise ValueError("invalid MCP tool name")
        if len(self.description) > 4096:
            raise ValueError("MCP tool description too long")
        input_schema = dict(self.input_schema)
        output_schema = dict(self.output_schema)
        annotations = dict(self.annotations)
        if input_schema.get("type") != "object":
            raise ValueError("MCP tool input schema must have object root")
        if output_schema.get("type") != "object":
            raise ValueError("MCP tool output schema must have object root")
        object.__setattr__(self, "input_schema", MappingProxyType(input_schema))
        object.__setattr__(self, "output_schema", MappingProxyType(output_schema))
        object.__setattr__(self, "annotations", MappingProxyType(annotations))

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            "outputSchema": dict(self.output_schema),
            "annotations": dict(self.annotations),
        }


@dataclass(frozen=True)
class MCPToolList:
    protocol_revision: str
    tools: tuple[MCPToolDescriptor, ...]
    ttl_ms: int
    cache_scope: str
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "protocolRevision": self.protocol_revision,
            "tools": [item.to_dict() for item in self.tools],
            "ttlMs": self.ttl_ms,
            "cacheScope": self.cache_scope,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class MCPRequestEnvelope:
    request_id: str
    method: str
    name: str
    arguments: Mapping[str, object]
    protocol_revision: str = MCP_PROTOCOL_REVISION
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id or len(self.request_id) > 160:
            raise ValueError("invalid MCP request_id")
        if not self.method or len(self.method) > 128:
            raise ValueError("invalid MCP method")
        if len(self.name) > 128:
            raise ValueError("invalid MCP tool name")
        arguments = dict(self.arguments)
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many MCP request metadata fields")
        object.__setattr__(self, "arguments", MappingProxyType(arguments))
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    @property
    def routing_headers(self) -> dict[str, str]:
        headers = {"Mcp-Method": self.method}
        if self.name:
            headers["Mcp-Name"] = self.name
        return headers

    def to_dict(self) -> dict[str, object]:
        return {
            "protocolRevision": self.protocol_revision,
            "requestId": self.request_id,
            "method": self.method,
            "name": self.name,
            "arguments": dict(self.arguments),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MCPResponseEnvelope:
    request_id: str
    ok: bool
    result: Mapping[str, object] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    protocol_revision: str = MCP_PROTOCOL_REVISION

    def __post_init__(self) -> None:
        result = dict(self.result)
        if len(self.error_code) > 128 or len(self.error_message) > 2048:
            raise ValueError("MCP response error field too long")
        if self.ok and (self.error_code or self.error_message):
            raise ValueError("successful MCP response cannot contain error fields")
        object.__setattr__(self, "result", MappingProxyType(result))

    def to_dict(self) -> dict[str, object]:
        return {
            "protocolRevision": self.protocol_revision,
            "requestId": self.request_id,
            "ok": self.ok,
            "result": dict(self.result),
            "error": None
            if self.ok
            else {"code": self.error_code, "message": self.error_message},
        }


class MCPToolSurface:
    """Export AI shell manifest tools without exposing host executable paths."""

    def __init__(
        self,
        manifest: AIToolManifest,
        *,
        ttl_ms: int = 30000,
        cache_scope: str = "public",
    ) -> None:
        if ttl_ms < 0:
            raise ValueError("MCP tool-list TTL may not be negative")
        if cache_scope not in {"public", "private", "no-store"}:
            raise ValueError("invalid MCP cache scope")
        self.manifest = manifest
        self.ttl_ms = ttl_ms
        self.cache_scope = cache_scope

    @staticmethod
    def _input_schema(tool: Mapping[str, object]) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 256,
                    "default": [],
                },
                "cwd": {"type": ["string", "null"]},
                "environmentRefs": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "maxProperties": 64,
                },
                "timeoutSeconds": {
                    "type": ["number", "null"],
                    "exclusiveMinimum": 0,
                },
                "purpose": {"type": "string", "maxLength": 1024},
            },
        }

    @staticmethod
    def _output_schema() -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok", "observationId"],
            "properties": {
                "ok": {"type": "boolean"},
                "observationId": {"type": "string"},
                "returncode": {"type": ["integer", "null"]},
                "timedOut": {"type": "boolean"},
                "outputLimited": {"type": "boolean"},
                "stdoutBytes": {"type": "integer", "minimum": 0},
                "stderrBytes": {"type": "integer", "minimum": 0},
                "stdoutDigest": {"type": "string"},
                "stderrDigest": {"type": "string"},
            },
        }

    def descriptors(self) -> tuple[MCPToolDescriptor, ...]:
        result = []
        for tool in self.manifest.tools:
            result.append(
                MCPToolDescriptor(
                    name=str(tool["name"]),
                    description=str(tool.get("description", "")),
                    input_schema=self._input_schema(tool),
                    output_schema=self._output_schema(),
                    annotations={
                        "effects": list(tool.get("effects", [])),
                        "idempotent": bool(tool.get("idempotent", False)),
                        "reversible": bool(tool.get("reversible", False)),
                        "approvalRecommended": bool(
                            tool.get("human_approval_recommended", True)
                        ),
                    },
                )
            )
        return tuple(result)

    def list_tools(self) -> MCPToolList:
        tools = self.descriptors()
        raw = json.dumps(
            [item.to_dict() for item in tools],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return MCPToolList(
            MCP_PROTOCOL_REVISION,
            tools,
            self.ttl_ms,
            self.cache_scope,
            hashlib.sha256(raw).hexdigest(),
        )
