"""Stable inventory of public xAI protobuf capabilities.

This module is descriptive only. It does not import generated protobuf objects
into canonical Skeleton contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class XAIToolCallType(str, Enum):
    CLIENT_SIDE = "client_side_tool"
    WEB_SEARCH = "web_search_tool"
    X_SEARCH = "x_search_tool"
    CODE_EXECUTION = "code_execution_tool"
    COLLECTIONS_SEARCH = "collections_search_tool"
    MCP = "mcp_tool"
    ATTACHMENT_SEARCH = "attachment_search_tool"
    IMAGE_GENERATION = "image_generation_tool"


class XAIReasoningEffort(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


@dataclass(frozen=True, slots=True)
class XAIProtoSurface:
    service: str
    operations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.service.strip() or not self.operations:
            raise ValueError("proto surface requires service and operations")
        if len(set(self.operations)) != len(self.operations):
            raise ValueError("proto operations must be unique")


PUBLIC_SURFACES: Final[tuple[XAIProtoSurface, ...]] = (
    XAIProtoSurface(
        service="Chat",
        operations=(
            "GetCompletion",
            "GetCompletionChunk",
            "StartDeferredCompletion",
            "GetDeferredCompletion",
            "GetStoredCompletion",
            "DeleteStoredCompletion",
            "CompactContext",
        ),
    ),
    XAIProtoSurface(
        service="Files",
        operations=("UploadFile", "ListFiles", "GetFile", "DeleteFile"),
    ),
    XAIProtoSurface(
        service="Image",
        operations=("GenerateImage",),
    ),
    XAIProtoSurface(
        service="Video",
        operations=("GenerateVideo",),
    ),
)


__all__ = [
    "PUBLIC_SURFACES",
    "XAIProtoSurface",
    "XAIReasoningEffort",
    "XAIToolCallType",
]
