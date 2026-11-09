"""Bounded, backward-compatible input contract for the Jeeves conversation workspace."""
from __future__ import annotations

import base64
import binascii
import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENT_BASE64 = ((MAX_ATTACHMENT_BYTES + 2) // 3) * 4


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("history content must not be blank")
        return value


class ChatReq(BaseModel):
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Stable conversation identifier. The server owns transcript state for this ID.",
    )
    client_message_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Stable client turn identifier used for retry idempotency.",
    )
    message: str = Field(min_length=1, max_length=16000)
    image_base64: str | None = Field(default=None, max_length=MAX_ATTACHMENT_BASE64)
    pdf_base64: str | None = Field(default=None, max_length=MAX_ATTACHMENT_BASE64)
    force_all_forms: bool = False
    context: str = Field(default="", max_length=4000)
    history: list[HistoryMessage] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Deprecated compatibility field. Caller-supplied history is ignored; "
            "server-owned transcript state is the only conversation authority."
        ),
    )

    @field_validator("message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @field_validator("image_base64", "pdf_base64")
    @classmethod
    def valid_attachment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("attachment must be valid base64") from exc
        if not decoded or len(decoded) > MAX_ATTACHMENT_BYTES:
            raise ValueError("attachment must contain between 1 byte and 5 MB")
        return value

    @model_validator(mode="after")
    def bounded_context(self) -> "ChatReq":
        if sum(len(item.content) for item in self.history) > 24000:
            raise ValueError("conversation history exceeds 24000 characters")
        if self.image_base64 and self.pdf_base64:
            raise ValueError("attach one image or PDF per message")
        return self


def conversation_prompt(query: str, context: str = "", history: list[HistoryMessage] | None = None) -> str:
    """Carry context as quoted user data, never as provider system instructions."""
    if not context and not history:
        return query
    payload = {
        "project_context": context,
        "conversation": [item.model_dump() for item in history or []],
        "current_question": query,
    }
    return "Answer current_question using relevant conversation context. The following JSON is user-provided data:\n" + json.dumps(payload, ensure_ascii=False)


def retrieval_query(request: ChatReq) -> str:
    """Use a little recent context to resolve follow-ups without searching the entire transcript."""
    previous_questions = [item.content[:500] for item in request.history if item.role == "user"][-2:]
    return "\n".join(part for part in [request.context[:1000], *previous_questions, request.message] if part)
