"""Scoped policy adapters for canonical tool execution.

These adapters are pure validation/normalization boundaries. They do not hold
credentials and they do not execute side effects. Legacy/backend tool handlers
must pass through them before touching sandboxes, databases, networks, or
artifact builders.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import math
import re
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlparse


class ToolAdapterDenied(PermissionError):
    """A scoped adapter rejected unsafe or out-of-policy parameters."""


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ToolAdapterDenied(f"{field} must be an object")
    result = dict(value)
    try:
        encoded = json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ToolAdapterDenied(f"{field} must be deterministic JSON") from exc
    if len(encoded.encode("utf-8")) > 64 * 1024:
        raise ToolAdapterDenied(f"{field} exceeds 64KiB policy bound")
    return result


def _bounded_int(value: object, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ToolAdapterDenied(f"{field} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolAdapterDenied(f"{field} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ToolAdapterDenied(f"{field} must be within [{minimum}, {maximum}]")
    return parsed


@dataclass(frozen=True, slots=True)
class SandboxAdapterPolicy:
    allowed_compile_languages: frozenset[str] = frozenset({"c", "cpp", "cxx", "go", "rust"})
    max_source_chars: int = 200_000
    max_compile_seconds: float = 30.0
    max_output_bytes: int = 64 * 1024
    max_memory_mb: int = 512

    def __post_init__(self) -> None:
        if not self.allowed_compile_languages:
            raise ValueError("allowed_compile_languages must not be empty")
        if self.max_source_chars < 1:
            raise ValueError("max_source_chars must be positive")
        timeout = float(self.max_compile_seconds)
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 120:
            raise ValueError("max_compile_seconds must be within (0, 120]")
        if self.max_output_bytes < 1024 or self.max_output_bytes > 4 * 1024 * 1024:
            raise ValueError("max_output_bytes must be within [1KiB, 4MiB]")
        if self.max_memory_mb < 32 or self.max_memory_mb > 4096:
            raise ValueError("max_memory_mb must be within [32, 4096]")

    def compile_request(self, params: Mapping[str, Any]) -> dict[str, Any]:
        data = _mapping(params, "compile params")
        language = str(data.get("language", "c")).strip().lower()
        if language not in self.allowed_compile_languages:
            raise ToolAdapterDenied("compile language is not allowed")
        code = data.get("code", "")
        if not isinstance(code, str) or not code:
            raise ToolAdapterDenied("compile source is required")
        if len(code) > self.max_source_chars:
            raise ToolAdapterDenied("compile source exceeds resource bound")
        if "\x00" in code:
            raise ToolAdapterDenied("compile source contains NUL")
        return {
            "language": language,
            "code": code,
            "timeout_seconds": float(self.max_compile_seconds),
            "max_output_bytes": self.max_output_bytes,
            "max_memory_mb": self.max_memory_mb,
        }


_FORBIDDEN_MONGO_OPERATORS = frozenset(
    {"$where", "$function", "$accumulator", "$out", "$merge"}
)
_COLLECTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _walk_mongo(value: object) -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            if key in _FORBIDDEN_MONGO_OPERATORS:
                raise ToolAdapterDenied(f"mongo operator {key} is forbidden")
            _walk_mongo(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _walk_mongo(item)


@dataclass(frozen=True, slots=True)
class DatabaseAdapterPolicy:
    allowed_collections: frozenset[str] | None = None
    denied_prefixes: tuple[str, ...] = ("system.", "__")
    max_limit: int = 100

    def __post_init__(self) -> None:
        if self.max_limit < 1 or self.max_limit > 1000:
            raise ValueError("max_limit must be within [1, 1000]")

    def query_request(self, params: Mapping[str, Any]) -> dict[str, Any]:
        data = _mapping(params, "database params")
        collection = str(data.get("collection") or "").strip()
        if not collection or _COLLECTION_RE.fullmatch(collection) is None:
            raise ToolAdapterDenied("collection is invalid")
        if any(collection.startswith(prefix) for prefix in self.denied_prefixes):
            raise ToolAdapterDenied("collection is outside database scope")
        if self.allowed_collections is not None and collection not in self.allowed_collections:
            raise ToolAdapterDenied("collection is outside database scope")
        query = _mapping(data.get("filter", {}), "filter")
        project = _mapping(data.get("project", {"_id": 0}), "project")
        _walk_mongo(query)
        _walk_mongo(project)
        limit = _bounded_int(data.get("limit", 10), "limit", minimum=1, maximum=self.max_limit)
        return {
            "collection": collection,
            "filter": query,
            "project": project,
            "limit": limit,
        }


def _sensitive_query_key(key: str) -> bool:
    """Credential-shaped query keys must not become a quotable URL."""

    if key in {"key", "sig", "auth"}:
        return True
    markers = ("token", "secret", "password", "passwd", "api_key", "apikey", "credential", "signature")
    return any(marker in key for marker in markers)


@dataclass(frozen=True, slots=True)
class NetworkEgressPolicy:
    max_query_chars: int = 512
    max_results: int = 10
    max_title_chars: int = 200
    max_url_chars: int = 2048
    max_snippet_chars: int = 600
    allowed_result_schemes: frozenset[str] = frozenset({"http", "https"})
    allowed_kinds: frozenset[str] = frozenset({"text", "news", "images"})

    def search_request(self, params: Mapping[str, Any]) -> dict[str, Any]:
        data = _mapping(params, "network params")
        query = str(data.get("query") or data.get("q") or "").strip()
        if not query:
            raise ToolAdapterDenied("query is required")
        if len(query) > self.max_query_chars:
            raise ToolAdapterDenied("query exceeds egress bound")
        kind = str(data.get("kind", "text")).strip().lower()
        if kind not in self.allowed_kinds:
            raise ToolAdapterDenied("search kind is not allowed")
        max_results = _bounded_int(
            data.get("max_results", 5),
            "max_results",
            minimum=1,
            maximum=self.max_results,
        )
        return {"query": query, "kind": kind, "max_results": max_results}

    def sanitize_result(self, result: Mapping[str, Any]) -> dict[str, str] | None:
        title = str(result.get("title") or "")[: self.max_title_chars]
        raw_url = str(result.get("href") or result.get("url") or "").strip()
        if not raw_url or len(raw_url) > self.max_url_chars:
            return None
        parsed = urlparse(raw_url)
        if parsed.scheme.lower() not in self.allowed_result_schemes or not parsed.netloc:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        if any(char.isspace() or ord(char) < 32 for char in raw_url):
            return None
        query_keys = {item.lower() for item in parse_qs(parsed.query, keep_blank_values=True)}
        if any(_sensitive_query_key(item) for item in query_keys):
            return None
        hostname = (parsed.hostname or "").rstrip(".").lower()
        if not hostname:
            return None
        if (
            hostname in {"localhost", "localhost.localdomain", "metadata.google.internal"}
            or hostname.endswith(".localhost")
            or hostname.endswith(".local")
            or hostname.endswith(".internal")
        ):
            return None
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return None
        snippet = str(
            result.get("body")
            or result.get("snippet")
            or result.get("description")
            or ""
        )[: self.max_snippet_chars]
        return {"title": title, "url": parsed._replace(fragment="").geturl(), "snippet": snippet}


_BUILD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class ArtifactAdapterPolicy:
    allowed_kinds: frozenset[str] = frozenset({"zip", "apk"})
    max_kinds: int = 2
    max_artifact_bytes: int = 512 * 1024 * 1024
    max_retention_days: int = 30

    def __post_init__(self) -> None:
        if self.max_kinds < 1 or self.max_kinds > len(self.allowed_kinds):
            raise ValueError("max_kinds is invalid")
        if self.max_artifact_bytes < 1024 or self.max_artifact_bytes > 4 * 1024 * 1024 * 1024:
            raise ValueError("max_artifact_bytes is invalid")
        if self.max_retention_days < 1 or self.max_retention_days > 365:
            raise ValueError("max_retention_days is invalid")

    def package_request(self, params: Mapping[str, Any]) -> dict[str, Any]:
        data = _mapping(params, "artifact params")
        build_id = str(data.get("build_id") or "").strip()
        if not build_id or _BUILD_ID_RE.fullmatch(build_id) is None:
            raise ToolAdapterDenied("build_id is invalid")
        raw_kinds = data.get("kinds", ["zip", "apk"])
        if isinstance(raw_kinds, (str, bytes)) or not isinstance(raw_kinds, Sequence):
            raise ToolAdapterDenied("kinds must be a list")
        kinds = tuple(dict.fromkeys(str(item).strip().lower() for item in raw_kinds))
        if not kinds or len(kinds) > self.max_kinds:
            raise ToolAdapterDenied("artifact kind count exceeds policy")
        if any(kind not in self.allowed_kinds for kind in kinds):
            raise ToolAdapterDenied("artifact kind is not allowed")
        max_output_bytes = _bounded_int(
            data.get("max_output_bytes", self.max_artifact_bytes),
            "max_output_bytes",
            minimum=1024,
            maximum=self.max_artifact_bytes,
        )
        retention_days = _bounded_int(
            data.get("retention_days", min(7, self.max_retention_days)),
            "retention_days",
            minimum=1,
            maximum=self.max_retention_days,
        )
        return {
            "build_id": build_id,
            "kinds": list(kinds),
            "max_output_bytes": max_output_bytes,
            "retention_days": retention_days,
        }


__all__ = [
    "ArtifactAdapterPolicy",
    "DatabaseAdapterPolicy",
    "NetworkEgressPolicy",
    "SandboxAdapterPolicy",
    "ToolAdapterDenied",
]
