"""Governed tool surface — policy, then port, then a stable result ref.

The adapter policies reject unsafe parameters. This surface is the execution
side of that contract: a canonical tool is registered on ToolRuntime, the
policy runs before any port is called, and the stored payload is what later
citation packing is allowed to quote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Mapping

from skeleton.skills.tool_adapters.policy import (
    ArtifactAdapterPolicy,
    DatabaseAdapterPolicy,
    NetworkEgressPolicy,
    SandboxAdapterPolicy,
    ToolAdapterDenied,
)
from skeleton.skills.tool_contract import ToolEffect, ToolExecutionRequest, ToolManifest
from skeleton.skills.tool_runtime import ToolRuntime, ToolRuntimeError


Port = Callable[[Mapping[str, Any]], Mapping[str, Any]]

_OBJECT = {"type": "object"}


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _ref(tool_id: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:24]
    return f"{tool_id}:{digest}"


@dataclass(frozen=True, slots=True)
class PortCall:
    tool_id: str
    request: dict[str, Any]


@dataclass
class GovernedToolSurface:
    """Four scoped tools sharing one result ledger."""

    database: Port
    network: Port
    sandbox: Port
    artifacts: Port
    database_policy: DatabaseAdapterPolicy = field(default_factory=DatabaseAdapterPolicy)
    network_policy: NetworkEgressPolicy = field(default_factory=NetworkEgressPolicy)
    sandbox_policy: SandboxAdapterPolicy = field(default_factory=SandboxAdapterPolicy)
    artifact_policy: ArtifactAdapterPolicy = field(default_factory=ArtifactAdapterPolicy)
    calls: list[PortCall] = field(default_factory=list)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)

    def register(self, runtime: ToolRuntime) -> tuple[ToolManifest, ...]:
        if not isinstance(runtime, ToolRuntime):
            raise TypeError("runtime must be a ToolRuntime")
        installed = (
            self._manifest(
                "repository.query",
                "Read a tenant collection through the database policy.",
                ToolEffect.READ_ONLY,
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["collection"],
                    "properties": {
                        "collection": {"type": "string", "minLength": 1, "maxLength": 128},
                        "filter": _OBJECT,
                        "project": _OBJECT,
                        "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                    },
                },
                30.0,
            ),
            self._manifest(
                "network.search",
                "Search outside the trust boundary through the egress policy.",
                ToolEffect.READ_ONLY,
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 512},
                        "kind": {"type": "string", "enum": ["text", "news", "images"]},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                },
                30.0,
            ),
            self._manifest(
                "sandbox.compile",
                "Compile source inside the sandbox resource policy.",
                ToolEffect.REVERSIBLE,
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["language", "code"],
                    "properties": {
                        "language": {"type": "string", "minLength": 1, "maxLength": 16},
                        "code": {"type": "string", "minLength": 1},
                    },
                },
                float(self.sandbox_policy.max_compile_seconds),
            ),
            self._manifest(
                "artifact.package",
                "Package a build artifact inside the retention policy.",
                ToolEffect.REVERSIBLE,
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["build_id"],
                    "properties": {
                        "build_id": {"type": "string", "minLength": 1, "maxLength": 128},
                        "kinds": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["zip", "apk"]},
                            "minItems": 1,
                            "maxItems": 2,
                        },
                        "max_output_bytes": {"type": "integer", "minimum": 1024},
                        "retention_days": {"type": "integer", "minimum": 1, "maximum": 365},
                    },
                },
                60.0,
            ),
        )
        handlers = {
            "repository.query": self._query,
            "network.search": self._search,
            "sandbox.compile": self._compile,
            "artifact.package": self._package,
        }
        for manifest in installed:
            runtime.register(manifest, handlers[manifest.tool_id])
        return installed

    def _manifest(
        self,
        tool_id: str,
        description: str,
        effect: ToolEffect,
        schema: dict[str, Any],
        timeout_seconds: float,
    ) -> ToolManifest:
        return ToolManifest(
            tool_id=tool_id,
            version="1",
            description=description,
            input_schema=schema,
            effect=effect,
            timeout_seconds=timeout_seconds,
        )

    def _store(self, tool_id: str, payload: Mapping[str, Any]) -> str:
        encoded = _canonical(payload)
        ref = _ref(tool_id, payload)
        self.results[ref] = json.loads(encoded)
        return ref

    def _invoke(self, tool_id: str, request: Mapping[str, Any], port: Port) -> Mapping[str, Any]:
        self.calls.append(PortCall(tool_id=tool_id, request=dict(request)))
        payload = port(request)
        if not isinstance(payload, Mapping):
            raise ToolRuntimeError("tool port must return an object")
        return payload

    def _query(self, request: ToolExecutionRequest) -> str:
        normalized = self.database_policy.query_request(request.arguments)
        payload = self._invoke("repository.query", normalized, self.database)
        rows = payload.get("rows")
        if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
            raise ToolRuntimeError("database port must return row objects")
        if len(rows) > int(normalized["limit"]):
            raise ToolRuntimeError("database port exceeded the admitted limit")
        return self._store("repository.query", {"kind": "database", "rows": [dict(row) for row in rows]})

    def _search(self, request: ToolExecutionRequest) -> str:
        normalized = self.network_policy.search_request(request.arguments)
        payload = self._invoke("network.search", normalized, self.network)
        raw_hits = payload.get("results", [])
        if not isinstance(raw_hits, list):
            raise ToolRuntimeError("network port must return a result list")
        hits = []
        for item in raw_hits:
            if not isinstance(item, Mapping):
                continue
            clean = self.network_policy.sanitize_result(item)
            if clean is not None:
                hits.append(clean)
            if len(hits) >= int(normalized["max_results"]):
                break
        return self._store("network.search", {"kind": "network", "hits": hits})

    def _compile(self, request: ToolExecutionRequest) -> str:
        normalized = self.sandbox_policy.compile_request(request.arguments)
        payload = self._invoke("sandbox.compile", normalized, self.sandbox)
        stdout = payload.get("stdout", "")
        exit_code = payload.get("exit_code", 0)
        if not isinstance(stdout, str) or isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ToolRuntimeError("sandbox port returned an invalid result")
        if len(stdout.encode("utf-8")) > int(normalized["max_output_bytes"]):
            raise ToolRuntimeError("sandbox output exceeds the resource bound")
        return self._store(
            "sandbox.compile",
            {"kind": "sandbox", "stdout": stdout, "exit_code": exit_code},
        )

    def _package(self, request: ToolExecutionRequest) -> str:
        normalized = self.artifact_policy.package_request(request.arguments)
        payload = self._invoke("artifact.package", normalized, self.artifacts)
        artifact_id = str(payload.get("artifact_id") or "")
        size = payload.get("bytes")
        if not artifact_id or isinstance(size, bool) or not isinstance(size, int):
            raise ToolRuntimeError("artifact port returned an invalid result")
        if size < 0 or size > int(normalized["max_output_bytes"]):
            raise ToolRuntimeError("artifact port exceeded the size bound")
        return self._store(
            "artifact.package",
            {
                "kind": "artifact",
                "artifact_id": artifact_id,
                "bytes": size,
                "build_id": normalized["build_id"],
            },
        )


__all__ = ["GovernedToolSurface", "PortCall"]
