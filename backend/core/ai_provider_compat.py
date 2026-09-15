"""Narrow compatibility facade for retiring ``emergentintegrations.llm.chat``.

Older backend call sites keep their historical builder/message surface while
supported text generation is routed through :mod:`core.ai_provider`. This is a
migration bridge, not a second provider runtime. New code must use
``ProviderRegistry`` / ``ProviderRequest`` directly.

Legacy provider/model hints are advisory. The configured ``AI_PROVIDER`` remains
authoritative, credentials come from the canonical provider environment, and
unsupported multimodal operations fail explicitly instead of fabricating data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.ai_provider import (
    AIMessage,
    ProviderRegistry,
    ProviderRequest,
    ProviderUnavailableError,
)


@dataclass(frozen=True, slots=True, init=False)
class UserMessage:
    """Legacy-compatible user message container."""

    text: str

    def __init__(self, text: str | None = None, **kwargs: Any) -> None:
        candidate = text
        if candidate is None:
            candidate = kwargs.pop("content", kwargs.pop("message", ""))
        object.__setattr__(self, "text", str(candidate))

    @property
    def content(self) -> str:
        return self.text


class ChatResponse(str):
    """String response that also exposes the legacy ``.content`` attribute."""

    @property
    def content(self) -> str:
        return str(self)


class LlmChat:
    """Builder-compatible facade backed by the canonical provider registry."""

    def __init__(
        self,
        *args: Any,
        api_key: str | None = None,
        session_id: str | None = None,
        system_message: str | None = None,
        **_: Any,
    ) -> None:
        positional = list(args)
        if api_key is None and positional:
            api_key = positional.pop(0)
        if session_id is None and positional:
            session_id = positional.pop(0)
        if system_message is None and positional:
            system_message = positional.pop(0)
        if positional:
            raise TypeError("LlmChat accepts at most three legacy positional arguments")

        # ``api_key`` is accepted solely for source compatibility. Credentials
        # are intentionally resolved by the canonical provider runtime so a
        # legacy universal key is never forwarded to an unrelated vendor API.
        self._legacy_api_key_present = bool(api_key)
        self.session_id = str(session_id or "")
        self.system_message = str(system_message or "")
        self._provider_hint: str | None = None
        self._model_hint: str | None = None
        self._max_output_tokens: int | None = None
        self._params: dict[str, Any] = {}
        self._history: list[AIMessage] = []

    def with_model(self, provider: str, model: str) -> "LlmChat":
        self._provider_hint = (provider or "").strip().lower() or None
        self._model_hint = (model or "").strip() or None
        return self

    def with_system_message(self, system_message: str) -> "LlmChat":
        self.system_message = str(system_message or "")
        return self

    def with_max_tokens(self, max_tokens: int) -> "LlmChat":
        self._max_output_tokens = max(1, int(max_tokens))
        return self

    def with_params(self, **params: Any) -> "LlmChat":
        self._params.update(params)
        raw_max = params.get("max_output_tokens", params.get("max_tokens"))
        if raw_max is not None:
            self._max_output_tokens = max(1, int(raw_max))
        return self

    def with_temperature(self, temperature: float) -> "LlmChat":
        # Accepted for migration compatibility. The neutral provider contract
        # does not currently expose sampling controls, so this remains metadata.
        self._params["temperature"] = float(temperature)
        return self

    def _prompt_text(self, message: Any) -> str:
        if isinstance(message, str):
            return message
        text = getattr(message, "text", None)
        if text is None:
            text = getattr(message, "content", None)
        if text is None:
            raise TypeError("legacy chat message must provide text/content")
        return str(text)

    async def send_message(self, message: Any) -> ChatResponse:
        prompt = self._prompt_text(message)
        registry = ProviderRegistry.from_env()
        adapter = registry.require_active()

        # Only honor a model hint when it belongs to the configured provider.
        # Cross-provider legacy hints (for example Claude/Gemini) must not make
        # an OpenAI request claim to be another provider.
        model = self._model_hint if self._provider_hint == adapter.provider_id else None
        response = await adapter.generate(
            ProviderRequest(
                instructions=self.system_message,
                prompt=prompt,
                history=tuple(self._history),
                max_output_tokens=self._max_output_tokens,
                model=model,
            )
        )
        self._history.append(AIMessage(role="user", content=prompt))
        self._history.append(AIMessage(role="assistant", content=response.text))
        return ChatResponse(response.text)

    async def chat(self, message: Any) -> ChatResponse:
        """Legacy alias for :meth:`send_message`."""

        return await self.send_message(message)

    async def generate(self, message: Any) -> ChatResponse:
        """Legacy alias for :meth:`send_message`."""

        return await self.send_message(message)

    async def send_message_multimodal_response(
        self, message: Any
    ) -> tuple[str, list[dict[str, Any]]]:
        del message
        raise ProviderUnavailableError(
            "legacy multimodal generation is not implemented by the canonical text provider runtime"
        )


__all__ = ["ChatResponse", "LlmChat", "UserMessage"]
