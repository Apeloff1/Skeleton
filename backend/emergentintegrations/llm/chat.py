"""Minimal compatibility layer for the retired Emergent LLM SDK.

``backend.server`` historically imported these names at module import time even
though the current server no longer uses them.  Keeping this tiny local surface
prevents an optional third-party SDK from becoming a hard boot dependency.

If legacy code starts using the objects again, construction remains compatible
and the first network-style operation fails loudly with an actionable message
instead of producing a misleading import error during application startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class UserMessage:
    """Import-compatible user message container used by historical call sites."""

    text: str

    def __init__(self, text: str | None = None, **kwargs: Any) -> None:
        candidate = text
        if candidate is None:
            candidate = kwargs.pop("content", kwargs.pop("message", ""))
        self.text = str(candidate)

    @property
    def content(self) -> str:
        return self.text


class LlmChat:
    """Boot-safe placeholder for the removed optional SDK client.

    The constructor intentionally accepts arbitrary positional/keyword options
    because several historical Emergent SDK releases used different parameter
    names.  No external behavior is emulated: attempts to send a message raise
    a deterministic error that points callers toward the maintained provider
    boundary.
    """

    __slots__ = ("args", "kwargs")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = dict(kwargs)

    @staticmethod
    def _unsupported() -> RuntimeError:
        return RuntimeError(
            "The optional emergentintegrations SDK is not installed. "
            "backend.server no longer requires it for boot; migrate active LLM "
            "calls to Skeleton's maintained provider/runtime integration."
        )

    async def send_message(self, *_args: Any, **_kwargs: Any) -> Any:
        raise self._unsupported()

    async def chat(self, *_args: Any, **_kwargs: Any) -> Any:
        raise self._unsupported()

    async def generate(self, *_args: Any, **_kwargs: Any) -> Any:
        raise self._unsupported()

    def with_model(self, *_args: Any, **_kwargs: Any) -> "LlmChat":
        return self

    def with_system_message(self, *_args: Any, **_kwargs: Any) -> "LlmChat":
        return self
