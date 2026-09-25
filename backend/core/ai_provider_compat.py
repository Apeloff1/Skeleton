"""Narrow compatibility facade for retired legacy LLM chat callers.

Older backend call sites retain their historical builder/message surface while
text generation is delegated to the canonical Skeleton engine. This module
does not read provider credentials, instantiate provider adapters, or perform
provider network transport.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from core.engine_text import (
    EngineTextError,
    EngineTextRequest,
    EngineTextResponse,
    execute_engine_text,
)
from skeleton.provider_runtime import ProviderUnavailableError


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
    """String response that also exposes the legacy content attribute."""

    @property
    def content(self) -> str:
        return str(self)


class LlmChat:
    """Builder-compatible facade backed by the canonical engine text adapter."""

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
            raise TypeError(
                "LlmChat accepts at most three legacy positional arguments"
            )

        self._legacy_api_key_present = bool(api_key)
        self.session_id = str(session_id or "")
        self.system_message = str(system_message or "")
        self._provider_hint: str | None = None
        self._model_hint: str | None = None
        self._max_output_tokens: int | None = None
        self._params: dict[str, Any] = {}
        self._history: list[dict[str, str]] = []

    def with_model(self, provider: str, model: str) -> "LlmChat":
        # Compatibility metadata only. Provider/model routing is engine-owned.
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
        # Accepted for migration compatibility. Sampling remains engine-owned.
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

    def _idempotency_key(self, prompt: str) -> str:
        material = json.dumps(
            {
                "session_id": self.session_id,
                "turn_index": len(self._history),
                "prompt": prompt,
                "history": self._history,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return "legacy-llm-chat:" + hashlib.sha256(material).hexdigest()

    async def send_message(self, message: Any) -> ChatResponse:
        prompt = self._prompt_text(message).strip()
        if not prompt:
            raise ValueError("legacy chat prompt must be non-empty")
        instructions = (
            self.system_message.strip()
            or "Respond helpfully to the user request."
        )
        request = EngineTextRequest(
            instructions=instructions,
            prompt=prompt,
            idempotency_key=self._idempotency_key(prompt),
            history=tuple(self._history),
            tenant_id="default",
            actor_id="legacy-llm-chat",
            capability="assistant.compat",
            max_output_tokens=self._max_output_tokens,
        )
        try:
            response: EngineTextResponse = await execute_engine_text(request)
        except EngineTextError as exc:
            raise ProviderUnavailableError(
                "canonical engine text execution is unavailable"
            ) from exc

        self._history.append({"role": "user", "content": prompt})
        self._history.append(
            {"role": "assistant", "content": response.text}
        )
        return ChatResponse(response.text)

    async def chat(self, message: Any) -> ChatResponse:
        """Legacy alias for send_message."""

        return await self.send_message(message)

    async def generate(self, message: Any) -> ChatResponse:
        """Legacy alias for send_message."""

        return await self.send_message(message)

    async def send_message_multimodal_response(
        self, message: Any
    ) -> tuple[str, list[dict[str, Any]]]:
        del message
        raise ProviderUnavailableError(
            "legacy multimodal generation is not implemented by the engine text compatibility boundary"
        )


__all__ = ["ChatResponse", "LlmChat", "UserMessage"]
