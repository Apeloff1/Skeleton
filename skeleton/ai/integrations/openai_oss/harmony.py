"""Optional OpenAI Harmony interoperability for local gpt-oss models."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import import_module
from typing import Callable, Iterable, Sequence

from .optional import load_optional
from .registry import source


@dataclass(frozen=True, slots=True)
class HarmonyInputMessage:
    role: str
    content: str
    channel: str | None = None
    recipient: str | None = None

    def __post_init__(self) -> None:
        if self.role not in {"system", "developer", "user", "assistant", "tool"}:
            raise ValueError("unsupported Harmony role")
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("Harmony message content must be non-empty")
        if self.channel is not None and not self.channel.strip():
            raise ValueError("channel must be non-empty when supplied")
        if self.recipient is not None and not self.recipient.strip():
            raise ValueError("recipient must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class HarmonyPrompt:
    tokens: tuple[int, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class HarmonyOutputMessage:
    role: str
    content: str
    channel: str | None
    recipient: str | None


class HarmonyGptOssCodec:
    """Encode/decode the response format required by gpt-oss.

    Analysis-channel messages are excluded from normalized user-facing output
    by default. Callers must opt in explicitly if they are building a research
    tool that needs raw model reasoning.
    """

    def __init__(
        self,
        *,
        importer: Callable[[str], object] = import_module,
    ) -> None:
        self._importer = importer
        self._module = None
        self._encoding = None

    def _runtime(self):
        if self._module is None:
            self._module = load_optional(
                source("harmony"), "openai_harmony", importer=self._importer
            )
        if self._encoding is None:
            names = self._module.HarmonyEncodingName
            self._encoding = self._module.load_harmony_encoding(
                names.HARMONY_GPT_OSS
            )
        return self._module, self._encoding

    def render_for_completion(
        self,
        messages: Sequence[HarmonyInputMessage],
    ) -> HarmonyPrompt:
        if not messages:
            raise ValueError("at least one Harmony message is required")
        module, encoding = self._runtime()
        rendered = []
        for item in messages:
            if not isinstance(item, HarmonyInputMessage):
                raise TypeError("messages must contain HarmonyInputMessage")
            role = module.Role(item.role)
            message = module.Message.from_role_and_content(role, item.content)
            if item.channel is not None:
                message = message.with_channel(item.channel)
            if item.recipient is not None:
                message = message.with_recipient(item.recipient)
            rendered.append(message)
        conversation = module.Conversation.from_messages(rendered)
        tokens = tuple(
            int(token)
            for token in encoding.render_conversation_for_completion(
                conversation,
                module.Role.ASSISTANT,
            )
        )
        digest = hashlib.sha256(
            ",".join(str(token) for token in tokens).encode("ascii")
        ).hexdigest()
        return HarmonyPrompt(tokens=tokens, digest=digest)

    @staticmethod
    def _message_text(message: object) -> str:
        parts: list[str] = []
        for content in getattr(message, "content", ()) or ():
            text = getattr(content, "text", None)
            if isinstance(text, str):
                parts.append(text)
                continue
            if hasattr(content, "to_dict"):
                payload = content.to_dict()
                value = payload.get("text") if isinstance(payload, dict) else None
                if isinstance(value, str):
                    parts.append(value)
        return "".join(parts)

    def parse_completion(
        self,
        tokens: Iterable[int],
        *,
        include_analysis: bool = False,
        strict: bool = True,
    ) -> tuple[HarmonyOutputMessage, ...]:
        module, encoding = self._runtime()
        parsed = encoding.parse_messages_from_completion_tokens(
            [int(token) for token in tokens],
            role=module.Role.ASSISTANT,
            strict=strict,
        )
        output: list[HarmonyOutputMessage] = []
        for message in parsed:
            channel = getattr(message, "channel", None)
            if channel == "analysis" and not include_analysis:
                continue
            role_obj = getattr(getattr(message, "author", None), "role", None)
            role = getattr(role_obj, "value", str(role_obj))
            output.append(
                HarmonyOutputMessage(
                    role=str(role),
                    content=self._message_text(message),
                    channel=channel,
                    recipient=getattr(message, "recipient", None),
                )
            )
        return tuple(output)


__all__ = [
    "HarmonyGptOssCodec",
    "HarmonyInputMessage",
    "HarmonyOutputMessage",
    "HarmonyPrompt",
]
