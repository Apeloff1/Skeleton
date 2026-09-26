"""Product-facing engine text chat facade.

This builder is intentionally provider-neutral. It compiles bounded text work
into the canonical backend EngineText boundary; it never reads provider
credentials, instantiates provider SDKs, or chooses a provider transport.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable

from core.engine_text import (
    EngineTextError,
    EngineTextRequest,
    EngineTextResponse,
    execute_engine_text,
)
from skeleton.context.instruction_policy import InstructionPolicy


@dataclass(frozen=True, slots=True, init=False)
class UserMessage:
    """Small product message container accepted by EngineChat."""

    text: str

    def __init__(
        self,
        text: str | None = None,
        **kwargs: Any,
    ) -> None:
        candidate = text
        if candidate is None:
            candidate = kwargs.pop(
                "content",
                kwargs.pop("message", ""),
            )
        object.__setattr__(self, "text", str(candidate))

    @property
    def content(self) -> str:
        return self.text


class EngineChatResponse(str):
    """String response with compatibility text/content properties."""

    @property
    def content(self) -> str:
        return str(self)

    @property
    def text(self) -> str:
        return str(self)


class EngineChat:
    """Bounded builder over canonical engine text execution."""

    def __init__(
        self,
        *args: Any,
        session_id: str | None = None,
        system_message: str | None = None,
        model: str | None = None,
        instruction_policy: InstructionPolicy | None = None,
        tenant_id: str = "default",
        actor_id: str = "backend-product",
        capability: str = "assistant.chat",
        verification_profile: str = "assistant_proposal",
        data_class: str = "internal",
        purpose: str = "model-inference",
        **_: Any,
    ) -> None:
        positional = list(args)
        if positional:
            # Historical callers sometimes supplied a credential positionally.
            # It is deliberately ignored; provider credentials are engine-owned.
            positional.pop(0)
        if session_id is None and positional:
            session_id = positional.pop(0)
        if system_message is None and positional:
            system_message = positional.pop(0)
        if positional:
            raise TypeError(
                "EngineChat accepts at most three compatibility positional arguments"
            )
        self.session_id = str(session_id or "")
        if instruction_policy is not None and not isinstance(
            instruction_policy,
            InstructionPolicy,
        ):
            raise TypeError(
                "instruction_policy must be InstructionPolicy"
            )
        explicit_system = str(system_message or "")
        if (
            instruction_policy is not None
            and explicit_system
            and explicit_system != instruction_policy.instructions
        ):
            raise ValueError(
                "system_message cannot override instruction_policy"
            )
        self.instruction_policy = instruction_policy
        self.system_message = (
            instruction_policy.instructions
            if instruction_policy is not None
            else explicit_system
        )
        self.tenant_id = str(tenant_id).strip()
        self.actor_id = str(actor_id).strip()
        self.capability = str(capability).strip()
        self.verification_profile = str(
            verification_profile
        ).strip()
        self.data_class = str(data_class).strip().lower()
        self.purpose = str(purpose).strip()
        if not all(
            (
                self.tenant_id,
                self.actor_id,
                self.capability,
                self.verification_profile,
                self.purpose,
            )
        ):
            raise ValueError(
                "engine chat runtime identity must be non-empty"
            )
        if self.data_class not in {
            "public",
            "internal",
            "confidential",
            "restricted",
        }:
            raise ValueError("engine chat data_class is invalid")
        self._provider_hint: str | None = None
        self._model_hint: str | None = (
            str(model).strip() if model else None
        )
        self._max_output_tokens: int | None = None
        self._params: dict[str, Any] = {}
        self._history: list[dict[str, str]] = []
        self._queued_prompt: str | None = None

    def with_model(self, provider: str, model: str) -> "EngineChat":
        # Routing metadata only; canonical engine policy owns provider choice.
        self._provider_hint = (provider or "").strip().lower() or None
        self._model_hint = (model or "").strip() or None
        return self

    def with_system_message(
        self,
        system_message: str,
    ) -> "EngineChat":
        if self.instruction_policy is not None:
            raise ValueError(
                "instruction policy owns system instructions"
            )
        self.system_message = str(system_message or "")
        return self

    def with_instruction_policy(
        self,
        policy: InstructionPolicy,
    ) -> "EngineChat":
        if not isinstance(policy, InstructionPolicy):
            raise TypeError("policy must be InstructionPolicy")
        if (
            self.system_message
            and self.system_message != policy.instructions
        ):
            raise ValueError(
                "existing system_message conflicts with policy"
            )
        self.instruction_policy = policy
        self.system_message = policy.instructions
        return self

    def with_max_tokens(self, max_tokens: int) -> "EngineChat":
        self._max_output_tokens = max(1, int(max_tokens))
        return self

    def with_params(self, **params: Any) -> "EngineChat":
        self._params.update(params)
        raw_max = params.get(
            "max_output_tokens",
            params.get("max_tokens"),
        )
        if raw_max is not None:
            self._max_output_tokens = max(1, int(raw_max))
        return self

    def with_temperature(
        self,
        temperature: float,
    ) -> "EngineChat":
        self._params["temperature"] = float(temperature)
        return self

    def add_message(
        self,
        role: str,
        content: str,
    ) -> "EngineChat":
        normalized_role = str(role).strip().lower()
        text = str(content)
        if normalized_role == "system":
            self.system_message = text
            return self
        if normalized_role == "user":
            self._queued_prompt = text
            return self
        if normalized_role == "assistant":
            self._history.append(
                {"role": "assistant", "content": text}
            )
            return self
        raise ValueError(
            "engine chat role must be system, user, or assistant"
        )

    @staticmethod
    def _prompt_text(message: Any) -> str:
        if isinstance(message, str):
            return message
        text = getattr(message, "text", None)
        if text is None:
            text = getattr(message, "content", None)
        if text is None:
            raise TypeError(
                "engine chat message must provide text/content"
            )
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
        return "engine-chat:" + hashlib.sha256(material).hexdigest()

    async def send_message(
        self,
        message: Any,
    ) -> EngineChatResponse:
        prompt = self._prompt_text(message).strip()
        if not prompt:
            raise ValueError(
                "engine chat prompt must be non-empty"
            )
        instructions = (
            self.system_message.strip()
            or "Respond helpfully to the user request."
        )
        policy = self.instruction_policy
        request = EngineTextRequest(
            instructions=instructions,
            prompt=prompt,
            idempotency_key=self._idempotency_key(prompt),
            instruction_policy_id=(
                None if policy is None else policy.policy_id
            ),
            instruction_policy_version=(
                None if policy is None else policy.version
            ),
            history=tuple(self._history),
            tenant_id=self.tenant_id,
            actor_id=self.actor_id,
            capability=self.capability,
            verification_profile=self.verification_profile,
            max_output_tokens=self._max_output_tokens,
            data_class=self.data_class,
            purpose=self.purpose,
        )
        response: EngineTextResponse = await execute_engine_text(
            request
        )
        self._history.append(
            {"role": "user", "content": prompt}
        )
        self._history.append(
            {"role": "assistant", "content": response.text}
        )
        return EngineChatResponse(response.text)

    async def chat(
        self,
        message: Any | None = None,
    ) -> EngineChatResponse:
        target = message
        if target is None:
            target = self._queued_prompt
            self._queued_prompt = None
        if target is None:
            raise ValueError(
                "engine chat requires a queued or explicit message"
            )
        return await self.send_message(target)

    async def generate(self, message: Any) -> EngineChatResponse:
        return await self.send_message(message)

    async def send_async(
        self,
        messages: Iterable[Any],
    ) -> EngineChatResponse:
        material = list(messages)
        if not material:
            raise ValueError(
                "engine chat messages must not be empty"
            )
        return await self.send_message(material[-1])

    async def send_message_multimodal_response(
        self,
        message: Any,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Text execution plus an empty artifact list.

        Product multimodal artifact generation must use a dedicated canonical
        artifact/media plane rather than a provider chat transport.
        """

        response = await self.send_message(message)
        return str(response), []


__all__ = [
    "EngineChat",
    "EngineChatResponse",
    "EngineTextError",
    "UserMessage",
]
