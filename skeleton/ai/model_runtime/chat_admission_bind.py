"""Bind a tokenizer digest to chat-admission submits. Parent #80. stored_prose=0."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json

from .admission_scheduler import RuntimeAdmissionScheduler
from .flgb_model_runtime import BatchRequest, ModelRuntimeError

_HEX = set("0123456789abcdef")


class ChatBindError(ModelRuntimeError):
    pass


def _hex64(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise ChatBindError("invalid tokenizer digest")
    return value


@dataclass(frozen=True, slots=True)
class ChatBound:
    request_id: str
    tokenizer_digest: str
    digest: str

    def card(self) -> dict[str, object]:
        return {
            "kind": "chat-admission-bind",
            "parent": "#80",
            "stored_prose": 0,
            "hit": 1,
            "request_id": self.request_id,
            "tokenizer_digest": self.tokenizer_digest,
            "digest": self.digest,
        }


class ChatAdmissionGate:
    def __init__(self, scheduler: RuntimeAdmissionScheduler, tokenizer_digest: str) -> None:
        if not isinstance(scheduler, RuntimeAdmissionScheduler):
            raise ChatBindError("RuntimeAdmissionScheduler required")
        self.scheduler = scheduler
        self.tokenizer_digest = _hex64(tokenizer_digest)
        self._bound: dict[str, str] = {}

    def submit(self, request: BatchRequest, *, kv_bytes: int, tokenizer_digest: str) -> ChatBound:
        digest = _hex64(tokenizer_digest)
        if not hmac.compare_digest(digest, self.tokenizer_digest):
            raise ChatBindError("tokenizer identity drift")
        if not isinstance(request, BatchRequest):
            raise ChatBindError("BatchRequest required")
        self.scheduler.submit(request, kv_bytes=kv_bytes)
        body = {"request_id": request.request_id, "tokenizer_digest": digest, "prompt_tokens": request.prompt_tokens}
        receipt = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        self._bound[request.request_id] = receipt
        return ChatBound(request.request_id, digest, receipt)


__all__ = ["ChatAdmissionGate", "ChatBindError", "ChatBound"]
