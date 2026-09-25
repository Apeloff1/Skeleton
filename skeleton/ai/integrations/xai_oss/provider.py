"""Optional provider edge for the official Apache-2.0 xAI Python SDK."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import os
from typing import Callable, Mapping
from urllib.parse import urlsplit

from .optional import load_optional
from .registry import source


@dataclass(frozen=True, slots=True)
class XAIProviderConfig:
    model: str
    api_host: str = "api.x.ai"
    timeout_seconds: float = 120.0
    store_messages: bool = False
    use_encrypted_content: bool = False
    parallel_tool_calls: bool = True
    max_turns: int = 8
    reasoning_effort: str | None = None
    allow_server_side_tools: bool = False
    allow_sensitive_telemetry: bool = False
    allow_insecure_local_channel: bool = False

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model must be non-empty")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 3600:
            raise ValueError("timeout_seconds must be in (0, 3600]")
        if not 1 <= self.max_turns <= 64:
            raise ValueError("max_turns must be in [1, 64]")
        if self.reasoning_effort not in {None, "none", "low", "medium", "high", "xhigh"}:
            raise ValueError("unsupported reasoning_effort")
        if not self.api_host.strip():
            raise ValueError("api_host must be non-empty")
        lowered = self.api_host.lower()
        if self.allow_insecure_local_channel and not (
            lowered.startswith("localhost:") or lowered.startswith("127.0.0.1:")
        ):
            raise ValueError("insecure xAI transport is allowed only for localhost")

    def chat_settings(self) -> dict[str, object]:
        settings: dict[str, object] = {
            "store_messages": self.store_messages,
            "use_encrypted_content": self.use_encrypted_content,
            "parallel_tool_calls": self.parallel_tool_calls,
            "max_turns": self.max_turns,
        }
        if self.reasoning_effort is not None:
            settings["reasoning_effort"] = self.reasoning_effort
        return settings

    def telemetry_environment(self) -> Mapping[str, str]:
        if self.allow_sensitive_telemetry:
            return {}
        return {"XAI_SDK_DISABLE_SENSITIVE_TELEMETRY_ATTRIBUTES": "1"}


class XAIProviderEdge:
    def __init__(
        self,
        config: XAIProviderConfig,
        *,
        importer: Callable[[str], object] = import_module,
    ) -> None:
        self.config = config
        self._importer = importer

    def create_client(self, *, api_key: str):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be supplied ephemerally and non-empty")
        if not self.config.allow_sensitive_telemetry:
            require_sensitive_telemetry_disabled()
        module = load_optional(
            source("xai-sdk-python"),
            "xai_sdk",
            importer=self._importer,
        )
        client_type = getattr(module, "Client", None)
        if client_type is None:
            raise TypeError("xai_sdk.Client is unavailable")
        return client_type(
            api_key=api_key,
            api_host=self.config.api_host,
            timeout=self.config.timeout_seconds,
            use_insecure_channel=self.config.allow_insecure_local_channel,
        )

    def create_chat(
        self,
        client: object,
        *,
        messages: list[object] | tuple[object, ...] | None = None,
        tools: list[object] | tuple[object, ...] = (),
        user: str | None = None,
    ):
        if tools and not self.config.allow_server_side_tools:
            raise PermissionError("xAI server-side tools are disabled by provider policy")
        chat_client = getattr(client, "chat", None)
        if chat_client is None or not hasattr(chat_client, "create"):
            raise TypeError("client does not expose xAI chat.create")
        kwargs = self.config.chat_settings()
        kwargs["messages"] = list(messages) if messages is not None else None
        kwargs["tools"] = list(tools) if tools else None
        kwargs["user"] = user
        return chat_client.create(self.config.model, **kwargs)


def require_sensitive_telemetry_disabled(
    environ: Mapping[str, str] | None = None,
) -> None:
    values = os.environ if environ is None else environ
    flag = values.get("XAI_SDK_DISABLE_SENSITIVE_TELEMETRY_ATTRIBUTES", "")
    if flag.lower() not in {"1", "true"}:
        raise RuntimeError(
            "sensitive xAI SDK telemetry attributes are not disabled in this runtime"
        )


__all__ = [
    "XAIProviderConfig",
    "XAIProviderEdge",
    "require_sensitive_telemetry_disabled",
]
