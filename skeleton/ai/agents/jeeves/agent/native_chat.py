"""Plain conversational Jeeves on the same durable GGUF ExecutionSpine.

A small local model need not support strict planning JSON to answer a user.
This chat façade exposes the existing native session API but checks every
returned byte against an independently reopened authoritative SQLite replay.

This is *not* a second LLM provider, independent chat database, token backend,
permission engine, web endpoint or replacement for strict agent execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import secrets
import threading
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.session_adapter import create
from skeleton.ai.runtime.operational_ai.laptop_runtime.session_policy import new_request_id
from skeleton.ai.runtime.operational_ai.laptop_runtime.turn_bridge import TurnBridge
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation, identifier, nonnegative, number, utf8,
)

from .native_source_fence import NativeSourceFence
from .native_receipt_boundary import receive_committed_turn
from .native_schema_boundary import verify_structured_native_output


class NativeChatHold(ValueError):
    """A chat operation is not proven safe or durably committed."""


@dataclass(frozen=True, slots=True)
class NativeChatTurn:
    session_id: str
    request_id: str
    text: str
    output_sha256: str
    model_sha256: str
    tokenizer_sha256: str
    prompt_tokens: int
    generated_tokens: int
    finish_reason: str
    replayed: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_chat_turn.v1",
            "session_id": self.session_id,
            "request_id": self.request_id,
            "answer": self.text,
            "output_sha256": self.output_sha256,
            "model_sha256": self.model_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
            "prompt_tokens": self.prompt_tokens,
            "generated_tokens": self.generated_tokens,
            "finish_reason": self.finish_reason,
            "replayed": self.replayed,
            "authoritative_commit": True,
            "device_qualified": False,
            "release_certified": False,
        }


class NativeJeevesChat:
    """One owner-bound local conversation; all state belongs to ExecutionSpine.

    Reopen only a session already owned by the same active model/tenant/subject.
    A caller-provided prior session ID is not trusted or created implicitly.
    Each request is bound to the complete prompt, seed and temperature by
    the existing native SQLite request identity and receipt hash chain.
    """

    def __init__(
        self, worker: Any, *, session_id: str | None = None,
        source_fence: NativeSourceFence | None = None,
    ) -> None:
        self.worker = worker
        self.identity = ActiveModel.from_supervisor(worker)
        if source_fence is not None:
            if type(source_fence) is not NativeSourceFence:
                raise NativeChatHold("canonical source fence required")
            if source_fence.principal != self.identity:
                raise NativeChatHold("source fence principal differs from chat")
            source_fence.assert_live(worker)
        self.source_fence = source_fence
        self.bridge = TurnBridge(worker)
        if session_id is None:
            self.session_id = create(worker)
        else:
            self.session_id = identifier(session_id, "chat session")
            # This owner-bound read checks the canonical principal and
            # verifies the exact transcript before accepting a replay.
            self.worker.spine.history(self.session_id)
            try:
                reopened_identity = ActiveModel.from_supervisor(self.worker)
            except (ContractViolation, ValueError, AttributeError) as exc:
                raise NativeChatHold(
                    "native principal changed during chat reopen"
                ) from exc
            if reopened_identity != self.identity:
                raise NativeChatHold("native principal changed during chat reopen")
        self._closed = False
        if self.source_fence is not None:
            self.source_fence.assert_live(self.worker)
        # Per-chat ordering: turn, SQLite transcript read and close are one
        # process-local critical section. Cross-process ownership stays in
        # the canonical ExecutionSpine and SessionGate.
        self._lock = threading.RLock()

    def _assert_current(self) -> None:
        """Deny stale session reads, writes and disclosures after a model swap.

        This check is independent of the model-generated answer and cannot
        grant permissions or reopen a foreign/closed SQLite session.
        """
        try:
            active = ActiveModel.from_supervisor(self.worker)
        except (ValueError, AttributeError) as exc:
            raise NativeChatHold("native principal unavailable") from exc
        if active != self.identity:
            raise NativeChatHold("native model or principal changed")
        if self.source_fence is not None:
            self.source_fence.assert_live(self.worker)
            if ActiveModel.from_supervisor(self.worker) != self.identity:
                raise NativeChatHold("native owner changed after source check")

    def turn(
        self,
        message: str,
        *,
        request_id: str | None = None,
        seed: int = 0,
        temperature: float = 0.8,
    ) -> NativeChatTurn:
        with self._lock:
            if self._closed:
                raise NativeChatHold("closed session cannot submit inference")
            prompt = utf8(message, maximum=self.worker.spine.limits.input_bytes)
            id_ = identifier(request_id if request_id is not None else new_request_id())
            seed = nonnegative(seed, maximum=2**32 - 1)
            temperature = number(temperature, minimum=0.000000001, maximum=2)
            self._assert_current()
            # The owner-bound spine verifies the request digest on replay.
            committed = self.worker.spine.replay(
                self.session_id, id_, prompt, seed=seed, temperature=temperature,
            )
            was_replayed = committed is not None
            self._assert_current()
            if committed is None:
                # Native exceptions retain their uncertain SQLite pending lease.
                # Never reissue that request automatically after a crash.
                try:
                    fresh = self.bridge.turn(
                        self.session_id, id_, prompt, seed=seed,
                        temperature=temperature,
                    )
                except ContractViolation as exc:
                    # The lower native bridge now proves the independent SQLite
                    # commit before returning. Preserve that fail-closed hold at
                    # the public Jeeves chat boundary, without broad exception
                    # swallowing or a second native call on an uncertain result.
                    raise NativeChatHold(
                        "native chat turn lacks an approved durable receipt"
                    ) from exc
                self._assert_current()
                committed = self.worker.spine.replay(
                    self.session_id, id_, prompt, seed=seed, temperature=temperature,
                )
                self._assert_current()
                if committed is None:
                    raise NativeChatHold("native chat lacks authoritative commit")
                if (fresh.get("text") != committed.get("text")
                    or fresh.get("output_sha256") != committed.get("output_sha256")):
                    raise NativeChatHold("native result disagrees with committed receipt")
            # Model identity may have changed after the first read or generation.
            # Never publish even committed private text through a stale chat owner.
            self._assert_current()
            verified = receive_committed_turn(
                committed, active=self.identity,
                session_id=self.session_id, native_request_id=id_,
                maximum_output_tokens=self.worker.spine.limits.max_output_tokens,
            )
            answer = verify_structured_native_output(
                verified.text, None,
                maximum_bytes=self.worker.spine.limits.response_bytes,
            )
            # An identity change during verification must not publish text.
            self._assert_current()
            return NativeChatTurn(
                self.session_id, id_, answer, verified.output_sha256,
                verified.model_sha256, verified.tokenizer_sha256,
                verified.prompt_tokens, verified.generated_tokens,
                verified.finish_reason, was_replayed,
            )

    def history(
        self, *, maximum_messages: int = 256,
        maximum_total_bytes: int = 8388608,
    ) -> tuple[dict, ...]:
        with self._lock:
            if self._closed:
                raise NativeChatHold("closed chat session")
            self._assert_current()
            if type(maximum_messages) is not int or not 1 <= maximum_messages <= 8192:
                raise NativeChatHold("invalid bounded history limit")
            if (type(maximum_total_bytes) is not int
                    or not 1 <= maximum_total_bytes <= 33554432):
                raise NativeChatHold("invalid bounded history byte ceiling")
            # Source of truth is the native, integrity-checked SQLite transcript.
            records = self.worker.spine.history(self.session_id)
            self._assert_current()
            if type(records) not in (tuple, list) or len(records) > maximum_messages:
                raise NativeChatHold("history exceeds caller's bound")
            result = []
            used_bytes = 0
            for item in records:
                if type(item) is not dict or item.get("role") not in ("user", "assistant"):
                    raise NativeChatHold("native transcript has invalid role")
                value = utf8(item.get("content"), maximum=131072)
                # Count actual UTF-8 content, never Unicode code points.
                # This is a whole-history privacy limit in addition to
                # per-message and caller-supplied message-count ceilings.
                used_bytes += len(value.encode("utf-8", "strict"))
                if used_bytes > maximum_total_bytes:
                    raise NativeChatHold("private SQLite history byte ceiling exhausted")
                result.append({"role": item["role"], "content": value})
            self._assert_current()
            return tuple(result)

    def close(self) -> bool:
        with self._lock:
            if self._closed:
                return False
            self._assert_current()
            closed = self.worker.spine.close(self.session_id)
            if type(closed) is not bool:
                raise NativeChatHold("native close response not boolean")
            self._closed = True
            self._assert_current()
            return closed


__all__ = ["NativeChatHold", "NativeChatTurn", "NativeJeevesChat"]
