"""Governed construction of xAI server-side tool declarations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from importlib import import_module
from typing import Callable, FrozenSet
from urllib.parse import urlparse

from .optional import load_optional
from .registry import source


class XAIToolKind(str, Enum):
    WEB_SEARCH = "web_search"
    X_SEARCH = "x_search"
    CODE_EXECUTION = "code_execution"
    COLLECTIONS_SEARCH = "collections_search"
    MCP = "mcp"
    IMAGE_GENERATION = "image_generation"


@dataclass(frozen=True, slots=True)
class WebSearchSpec:
    allowed_domains: tuple[str, ...] = ()
    excluded_domains: tuple[str, ...] = ()
    enable_image_understanding: bool = False
    enable_image_search: bool = False
    user_location_country: str | None = None
    user_location_city: str | None = None
    user_location_region: str | None = None
    user_location_timezone: str | None = None

    def __post_init__(self) -> None:
        if self.allowed_domains and self.excluded_domains:
            raise ValueError("allowed_domains and excluded_domains are mutually exclusive")
        if len(self.allowed_domains) > 5 or len(self.excluded_domains) > 5:
            raise ValueError("xAI web-search domain filters are limited to five entries")
        for domain in (*self.allowed_domains, *self.excluded_domains):
            if (
                not domain
                or "://" in domain
                or "/" in domain
                or domain.startswith(".")
                or domain.endswith(".")
            ):
                raise ValueError(f"invalid web-search domain: {domain!r}")


@dataclass(frozen=True, slots=True)
class XSearchSpec:
    from_date: datetime | None = None
    to_date: datetime | None = None
    allowed_handles: tuple[str, ...] = ()
    excluded_handles: tuple[str, ...] = ()
    enable_image_understanding: bool = False
    enable_video_understanding: bool = False

    def __post_init__(self) -> None:
        if self.allowed_handles and self.excluded_handles:
            raise ValueError("allowed_handles and excluded_handles are mutually exclusive")
        if self.from_date is not None and self.to_date is not None:
            if self.from_date > self.to_date:
                raise ValueError("from_date must not be after to_date")
        for handle in (*self.allowed_handles, *self.excluded_handles):
            if not handle or handle.startswith("@") or any(ch.isspace() for ch in handle):
                raise ValueError(f"invalid X handle: {handle!r}")


@dataclass(frozen=True, slots=True)
class CollectionsSearchSpec:
    collection_ids: tuple[str, ...]
    limit: int | None = None
    instructions: str | None = None
    retrieval_mode: str | None = None

    def __post_init__(self) -> None:
        if not self.collection_ids or len(self.collection_ids) > 10:
            raise ValueError("collection_ids must contain between one and ten ids")
        if len(set(self.collection_ids)) != len(self.collection_ids):
            raise ValueError("collection_ids must be unique")
        if any(not item.strip() for item in self.collection_ids):
            raise ValueError("collection ids must be non-empty")
        if self.limit is not None and self.limit <= 0:
            raise ValueError("limit must be positive")
        if self.retrieval_mode not in {None, "hybrid", "semantic", "keyword"}:
            raise ValueError("unsupported retrieval_mode")


@dataclass(frozen=True, slots=True)
class McpSpec:
    server_url: str
    allowed_tool_names: tuple[str, ...]
    server_label: str | None = None
    server_description: str | None = None

    def __post_init__(self) -> None:
        parsed = urlparse(self.server_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("remote MCP endpoints must use an absolute https URL")
        if not self.allowed_tool_names:
            raise ValueError("MCP requires an explicit non-empty tool allowlist")
        if len(set(self.allowed_tool_names)) != len(self.allowed_tool_names):
            raise ValueError("MCP tool allowlist must be unique")
        if any(not name.strip() for name in self.allowed_tool_names):
            raise ValueError("MCP tool names must be non-empty")


@dataclass(frozen=True, slots=True)
class ImageGenerationSpec:
    action: str = "auto"

    def __post_init__(self) -> None:
        if self.action not in {"auto", "generate", "edit"}:
            raise ValueError("image action must be auto, generate, or edit")


@dataclass(frozen=True, slots=True)
class XAIServerToolPolicy:
    allowed_kinds: FrozenSet[XAIToolKind] = frozenset()

    def allows(self, kind: XAIToolKind) -> bool:
        normalized = kind if isinstance(kind, XAIToolKind) else XAIToolKind(str(kind))
        return normalized in self.allowed_kinds

    def require(self, kind: XAIToolKind) -> None:
        if not self.allows(kind):
            raise PermissionError(f"xAI server-side tool not admitted: {kind.value}")


class XAIToolBuilder:
    def __init__(
        self,
        policy: XAIServerToolPolicy,
        *,
        importer: Callable[[str], object] = import_module,
    ) -> None:
        self.policy = policy
        self._importer = importer

    def _tools(self):
        load_optional(source("xai-sdk-python"), "xai_sdk", importer=self._importer)
        return self._importer("xai_sdk.tools")

    def web_search(self, spec: WebSearchSpec):
        self.policy.require(XAIToolKind.WEB_SEARCH)
        module = self._tools()
        return module.web_search(
            excluded_domains=list(spec.excluded_domains) or None,
            allowed_domains=list(spec.allowed_domains) or None,
            enable_image_understanding=spec.enable_image_understanding,
            enable_image_search=spec.enable_image_search,
            user_location_country=spec.user_location_country,
            user_location_city=spec.user_location_city,
            user_location_region=spec.user_location_region,
            user_location_timezone=spec.user_location_timezone,
        )

    def x_search(self, spec: XSearchSpec):
        self.policy.require(XAIToolKind.X_SEARCH)
        module = self._tools()
        return module.x_search(
            from_date=spec.from_date,
            to_date=spec.to_date,
            allowed_x_handles=list(spec.allowed_handles) or None,
            excluded_x_handles=list(spec.excluded_handles) or None,
            enable_image_understanding=spec.enable_image_understanding,
            enable_video_understanding=spec.enable_video_understanding,
        )

    def code_execution(self):
        self.policy.require(XAIToolKind.CODE_EXECUTION)
        return self._tools().code_execution()

    def collections_search(self, spec: CollectionsSearchSpec):
        self.policy.require(XAIToolKind.COLLECTIONS_SEARCH)
        return self._tools().collections_search(
            collection_ids=list(spec.collection_ids),
            limit=spec.limit,
            instructions=spec.instructions,
            retrieval_mode=spec.retrieval_mode,
        )

    def mcp(
        self,
        spec: McpSpec,
        *,
        authorization: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        self.policy.require(XAIToolKind.MCP)
        module = self._tools()
        return module.mcp(
            server_url=spec.server_url,
            server_label=spec.server_label,
            server_description=spec.server_description,
            allowed_tool_names=list(spec.allowed_tool_names),
            authorization=authorization,
            extra_headers=extra_headers,
        )

    def image_generation(self, spec: ImageGenerationSpec):
        self.policy.require(XAIToolKind.IMAGE_GENERATION)
        return self._tools().image_generation(action=spec.action)


__all__ = [
    "CollectionsSearchSpec",
    "ImageGenerationSpec",
    "McpSpec",
    "WebSearchSpec",
    "XAIServerToolPolicy",
    "XAIToolBuilder",
    "XAIToolKind",
    "XSearchSpec",
]
