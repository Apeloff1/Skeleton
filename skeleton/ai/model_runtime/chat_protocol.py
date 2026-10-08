"""Bounded, deterministic role-based chat protocol for native token generation.

Explicit framing and escaping prevent user-supplied text from impersonating a
system or assistant role. The protocol is transport-agnostic and does not
promise that the model has been instruction-tuned for this format.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping

from .runtime_contracts import RuntimeContractError

ROLES = ("system", "developer", "user", "assistant", "tool")
MAX_MESSAGE_BYTES = 262144
MAX_TRANSCRIPT_BYTES = 2097152
MAX_MESSAGES = 2048


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    name: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise RuntimeContractError("unsupported chat role")
        if type(self.role) is not str or self.role not in ROLES:
            raise RuntimeContractError("unsupported chat role")
        if not isinstance(self.content, str):
            raise RuntimeContractError("chat content must be text")
        if len(self.content.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise RuntimeContractError("chat message exceeds byte budget")
        if self.name is not None:
            if not isinstance(self.name, str) or not 1 <= len(self.name) <= 64:
                raise RuntimeContractError("invalid chat participant name")
            if not all(c.isascii() and (c.isalnum() or c in "_-") for c in self.name):
                raise RuntimeContractError("invalid chat participant name")

    def to_dict(self) -> dict[str, str]:
        result = {"role": self.role, "content": self.content}
        if self.name is not None:
            result["name"] = self.name
        return result


@dataclass(frozen=True)
class ChatTranscript:
    messages: tuple[ChatMessage, ...]

    def __post_init__(self) -> None:
        if len(self.messages) > MAX_MESSAGES:
            raise RuntimeContractError("too many chat messages")
        if any(not isinstance(message, ChatMessage) for message in self.messages):
            raise RuntimeContractError("invalid chat message")
        if sum(len(m.content.encode("utf-8")) for m in self.messages) > MAX_TRANSCRIPT_BYTES:
            raise RuntimeContractError("transcript exceeds byte budget")

    @classmethod
    def parse(cls, data: Iterable[Mapping[str, str]]) -> "ChatTranscript":
        if isinstance(data, (str, bytes, Mapping)):
            raise RuntimeContractError("transcript requires a message iterable")
        messages = []
        for item in data:
            if len(messages) >= MAX_MESSAGES:
                raise RuntimeContractError("too many chat messages")
            if not isinstance(item, Mapping):
                raise RuntimeContractError("invalid chat message")
            if set(item) - {"role", "content", "name"}:
                raise RuntimeContractError("unknown chat message fields")
            messages.append(ChatMessage(item.get("role"), item.get("content"),
                                        item.get("name")))
        return cls(tuple(messages))

    def append(self, role: str, content: str, name: str | None = None) -> "ChatTranscript":
        return ChatTranscript(self.messages + (ChatMessage(role, content, name),))

    def without_system(self) -> "ChatTranscript":
        return ChatTranscript(tuple(m for m in self.messages if m.role != "system"))

    def tail(self, count: int) -> "ChatTranscript":
        if type(count) is not int or count < 0:
            raise RuntimeContractError("invalid transcript tail")
        return ChatTranscript(self.messages[-count:] if count else ())

    def count_by_role(self) -> dict[str, int]:
        counts = {role: 0 for role in ROLES}
        for message in self.messages:
            counts[message.role] += 1
        return counts

    def byte_size(self) -> int:
        return sum(len(message.content.encode("utf-8")) for message in self.messages)

    def select_roles(self, roles: Iterable[str]) -> "ChatTranscript":
        selected = frozenset(roles)
        if not selected.issubset(ROLES):
            raise RuntimeContractError("unknown chat role filter")
        return ChatTranscript(tuple(m for m in self.messages if m.role in selected))

    def drop_first(self, count: int) -> "ChatTranscript":
        if type(count) is not int or count < 0:
            raise RuntimeContractError("invalid drop count")
        return ChatTranscript(self.messages[count:])

    def replace_last(self, role: str, content: str) -> "ChatTranscript":
        if not self.messages:
            raise RuntimeContractError("cannot replace empty transcript")
        return ChatTranscript(self.messages[:-1] + (ChatMessage(role, content),))

    def last_role(self) -> str | None:
        return self.messages[-1].role if self.messages else None

    def last_user_message(self) -> ChatMessage | None:
        return next((m for m in reversed(self.messages) if m.role == "user"), None)

    def last_assistant_message(self) -> ChatMessage | None:
        return next((m for m in reversed(self.messages) if m.role == "assistant"), None)

    def merge(self, other: "ChatTranscript") -> "ChatTranscript":
        if not isinstance(other, ChatTranscript):
            raise RuntimeContractError("transcript required")
        return ChatTranscript(self.messages + other.messages)

    def fits_bytes(self, budget: int) -> bool:
        if type(budget) is not int or budget < 0:
            raise RuntimeContractError("invalid byte budget")
        return self.byte_size() <= budget

    def trim_to_bytes(self, budget: int, *, preserve_instructions: bool = True) -> "ChatTranscript":
        if type(budget) is not int or budget < 0:
            raise RuntimeContractError("invalid byte budget")
        instructions = tuple(m for m in self.messages
                             if m.role in ("system", "developer")) if preserve_instructions else ()
        remaining = budget - sum(len(m.content.encode("utf-8")) for m in instructions)
        if remaining < 0:
            raise RuntimeContractError("instruction messages exceed byte budget")
        kept = []
        for m in reversed(self.messages):
            if preserve_instructions and m.role in ("system", "developer"):
                continue
            size = len(m.content.encode("utf-8"))
            if size > remaining:
                break
            kept.append(m)
            remaining -= size
        return ChatTranscript(instructions + tuple(reversed(kept)))

    def digest(self) -> str:
        payload = json.dumps(self.to_list(), ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_list(self) -> list[dict[str, str]]:
        return [m.to_dict() for m in self.messages]

    def to_json(self) -> str:
        return json.dumps(self.to_list(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> "ChatTranscript":
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > MAX_TRANSCRIPT_BYTES + 262144:
            raise RuntimeContractError("invalid transcript JSON budget")
        try:
            data = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise RuntimeContractError("invalid transcript JSON") from exc
        if not isinstance(data, list):
            raise RuntimeContractError("transcript must be a list")
        return cls.parse(data)

    def format_prompt(self, *, assistant_prefix: bool = True) -> str:
        """Length-delimited framing makes role delimiters unambiguous."""
        chunks = []
        for message in self.messages:
            content = message.content
            size = len(content.encode("utf-8"))
            name = message.name or ""
            chunks.append(f"[message role={message.role} name={name} bytes={size}]\n"
                          + content + "\n[/message]\n")
        if assistant_prefix:
            chunks.append("[message role=assistant name= bytes=?]\n")
        return "".join(chunks)

    def latest_user_index(self) -> int | None:
        return next((i for i in range(len(self.messages) - 1, -1, -1)
                     if self.messages[i].role == "user"), None)

    def dialogue_turns(self) -> tuple["ChatTranscript", ...]:
        """Group dialogue by user turn, retaining attached assistant/tool output."""
        groups: list[list[ChatMessage]] = []
        for message in self.messages:
            if message.role == "user":
                groups.append([message])
            elif message.role in ("assistant", "tool"):
                if not groups:
                    raise RuntimeContractError("orphan dialogue response")
                groups[-1].append(message)
        return tuple(ChatTranscript(tuple(group)) for group in groups)

    def validate_turn_order(self) -> None:
        """Require user/assistant turns after optional initial instructions."""
        active = False
        for index, message in enumerate(self.messages):
            if message.role in ("system", "developer"):
                if active:
                    raise RuntimeContractError("instruction messages must precede dialogue")
            elif message.role == "user":
                active = True
            elif message.role == "assistant":
                if not active:
                    raise RuntimeContractError("assistant turn without user input")
            elif message.role == "tool":
                if index == 0 or self.messages[index - 1].role != "assistant":
                    raise RuntimeContractError("tool result must follow assistant message")


__all__ = ["ChatMessage", "ChatTranscript"]
