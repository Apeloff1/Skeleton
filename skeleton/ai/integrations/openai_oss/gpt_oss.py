"""Governed descriptors for OpenAI's open-weight gpt-oss family."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import sys
from typing import FrozenSet

from .optional import OptionalDependencyError, dependency_status
from .registry import source


class GptOssModel(str, Enum):
    GPT_OSS_20B = "gpt-oss-20b"
    GPT_OSS_120B = "gpt-oss-120b"


class ReasoningEffort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_ALLOWED_TOOLS = frozenset({"browser", "python", "apply_patch"})


@dataclass(frozen=True, slots=True)
class GptOssRuntimeConfig:
    model: GptOssModel = GptOssModel.GPT_OSS_20B
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    enabled_tools: FrozenSet[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.model, GptOssModel):
            object.__setattr__(self, "model", GptOssModel(str(self.model)))
        if not isinstance(self.reasoning_effort, ReasoningEffort):
            object.__setattr__(
                self, "reasoning_effort", ReasoningEffort(str(self.reasoning_effort))
            )
        tools = frozenset(str(tool).strip() for tool in self.enabled_tools)
        unknown = tools - _ALLOWED_TOOLS
        if unknown:
            raise ValueError(f"unsupported gpt-oss tools: {sorted(unknown)}")
        object.__setattr__(self, "enabled_tools", tools)


@dataclass(frozen=True, slots=True)
class GptOssRuntimeStatus:
    python_compatible: bool
    package_available: bool
    package_version: str | None
    harmony_required: bool = True
    reason: str | None = None


def runtime_status() -> GptOssRuntimeStatus:
    metadata = source("gpt-oss")
    compatible = sys.version_info[:2] >= (metadata.minimum_python or (0, 0))
    if not compatible:
        return GptOssRuntimeStatus(
            python_compatible=False,
            package_available=False,
            package_version=None,
            reason="gpt-oss package requires Python >= 3.12",
        )
    status = dependency_status(metadata, "gpt_oss")
    return GptOssRuntimeStatus(
        python_compatible=True,
        package_available=status.available,
        package_version=status.package_version,
        reason=status.reason,
    )


def require_runtime() -> None:
    status = runtime_status()
    if not status.python_compatible or not status.package_available:
        raise OptionalDependencyError(status.reason or "gpt-oss runtime unavailable")


__all__ = [
    "GptOssModel",
    "GptOssRuntimeConfig",
    "GptOssRuntimeStatus",
    "ReasoningEffort",
    "require_runtime",
    "runtime_status",
]
