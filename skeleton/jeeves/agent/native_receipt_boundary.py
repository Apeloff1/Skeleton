"""Verify native transcript receipts before admitting them to Jeeves.

The native ExecutionSpine is the authoritative source. This module checks
identity and reply binding again at the Jeeves boundary, without accepting
caller-supplied success receipts as release or hardware evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.result_protocol import verify_turn_receipt


class NativeReceiptError(ValueError):
    """The native output cannot be treated as a committed Jeeves response."""


@dataclass(frozen=True, slots=True)
class VerifiedNativeReceipt:
    text: str
    output_sha256: str
    prompt_tokens: int
    generated_tokens: int
    finish_reason: str
    replayed: bool
    session_id: str
    native_request_id: str
    model_sha256: str
    tokenizer_sha256: str


def receive_committed_turn(
    record: Any,
    *,
    active: ActiveModel,
    session_id: str,
    native_request_id: str,
    maximum_output_tokens: int,
) -> VerifiedNativeReceipt:
    if not isinstance(active, ActiveModel):
        raise NativeReceiptError("active native identity required")
    if type(record) is not dict:
        raise NativeReceiptError("typed native receipt required")
    try:
        verified = verify_turn_receipt(
            record, model_sha256=active.model_sha256,
            tokenizer_sha256=active.tokenizer_sha256,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise NativeReceiptError("native receipt integrity invalid") from exc
    if verified.get("session") != session_id or verified.get("request_id") != native_request_id:
        raise NativeReceiptError("native receipt belongs to another request")
    if type(verified.get("finish_reason")) is not str or verified["finish_reason"] not in {
        "stop", "length", "eos"
    }:
        raise NativeReceiptError("unknown native finish reason")
    if (
        type(verified.get("generated_tokens")) is not int
        or verified["generated_tokens"] > maximum_output_tokens
    ):
        raise NativeReceiptError("native output exceeds Jeeves budget")
    if (
        type(verified.get("prompt_tokens")) is not int
        or verified["prompt_tokens"] < 0
    ):
        raise NativeReceiptError("native input metering invalid")
    if not verified["text"].strip():
        raise NativeReceiptError("empty native output not admitted")
    if sha256(verified["text"].encode("utf-8", "strict")).hexdigest() != verified["output_sha256"]:
        raise NativeReceiptError("native output bytes disagree with receipt")
    return VerifiedNativeReceipt(
        text=verified["text"],
        output_sha256=verified["output_sha256"],
        prompt_tokens=verified["prompt_tokens"],
        generated_tokens=verified["generated_tokens"],
        finish_reason=verified["finish_reason"],
        replayed=verified["replayed"],
        session_id=session_id,
        native_request_id=native_request_id,
        model_sha256=active.model_sha256,
        tokenizer_sha256=active.tokenizer_sha256,
    )


__all__ = ["NativeReceiptError", "VerifiedNativeReceipt", "receive_committed_turn"]
