"""Stateless MCP-2026-style export surface for AI shell tools.

This module is transport-agnostic. It emits deterministic tool descriptors,
self-describing request envelopes, routing headers, and cache hints while
leaving authorization and execution in the existing AI shell service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import unicodedata
from types import MappingProxyType
from typing import Iterable, Mapping

from skeleton.security.text_identity import require_authority_identifier
from skeleton.shells.ai.manifest import AIToolManifest

MCP_PROTOCOL_REVISION = "2026-07-28"
_TRUSTED_DESCRIPTION_ORIGIN = "repository_command_catalog"
_BIDI_OVERRIDE_CLASSES = frozenset({"RLE", "LRE", "RLO", "LRO", "PDF", "RLI", "LRI", "FSI", "PDI"})


def _validate_curated_description(value: str, origin: str) -> str:
    if origin != _TRUSTED_DESCRIPTION_ORIGIN:
        raise ValueError("MCP tool description must come from curated repository catalog")
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("invalid MCP tool description")
    if unicodedata.normalize("NFKC", value) != value:
        raise ValueError("MCP tool description must be compatibility-normalized")
    for char in value:
        category = unicodedata.category(char)
        if unicodedata.bidirectional(char) in _BIDI_OVERRIDE_CLASSES:
            raise ValueError("MCP tool description contains bidi controls")
        if category in {"Cf", "Cs"}:
            raise ValueError("MCP tool description contains invisible controls")
        if category == "Cc" and char not in {"\n", "\r", "\t"}:
            raise ValueError("MCP tool description contains control characters")
    return value


@dataclass(frozen=True)
class MCPToolDescriptor:
    name: str
    description: str
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]
    annotations: Mapping[str, object] = field(default_factory=dict)
    description_origin: str = _TRUSTED_DESCRIPTION_ORIGIN

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 128:
            raise ValueError("invalid MCP tool name")
        require_authority_identifier(
            self.name,
            field="MCP tool name",
            max_length=128,
        )
        _validate_curated_description(self.description, self.description_origin)
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
            "descriptionOrigin": self.description_origin,
            "descriptionInstructionAuthority": False,
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
        require_authority_identifier(
            self.request_id,
            field="MCP request_id",
            max_length=160,
        )
        require_authority_identifier(
            self.method,
            field="MCP method",
            max_length=128,
        )
        if self.name:
            require_authority_identifier(
                self.name,
                field="MCP tool name",
                max_length=128,
            )
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
                        "descriptionInstructionAuthority": False,
                    },
                    description_origin=str(tool.get("description_origin", "")),
                )
            )
        return tuple(result)

    def list_tools(
        self,
        *,
        allowed_names: Iterable[str] | None = None,
        cache_scope: str | None = None,
    ) -> MCPToolList:
        tools = self.descriptors()
        if allowed_names is not None:
            allowed = frozenset(allowed_names)
            tools = tuple(item for item in tools if item.name in allowed)
        effective_cache_scope = self.cache_scope if cache_scope is None else cache_scope
        if effective_cache_scope not in {"public", "private", "no-store"}:
            raise ValueError("invalid MCP cache scope")
        raw = json.dumps(
            [item.to_dict() for item in tools],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return MCPToolList(
            MCP_PROTOCOL_REVISION,
            tools,
            self.ttl_ms,
            effective_cache_scope,
            hashlib.sha256(raw).hexdigest(),
        )
