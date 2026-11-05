"""One installed GGUF model, many principal-bound Jeeves conversations.

No HTTP listener, hosted model, implicit tool use, or separate state owner.
Input is one UTF-8 message per line; transcript identity and committed answers
are produced by the existing native SQLite authority. An uncertain native
call stops the interactive session without automatically issuing a retry.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, BinaryIO, TextIO

from .native_chat import NativeChatHold, NativeJeevesChat
from .native_source_fence import NativeSourceFence


class NativeReplHold(ValueError):
    """An interactive session crossed an explicit admission limit."""


@dataclass(frozen=True, slots=True)
class ReplLimits:
    max_turns: int = 128
    max_input_bytes: int = 32768
    max_answer_bytes: int = 262144
    max_history_messages: int = 128

    def __post_init__(self):
        limits = (
            ("max_turns", self.max_turns, 1, 4096),
            ("max_input_bytes", self.max_input_bytes, 1, 1048576),
            ("max_answer_bytes", self.max_answer_bytes, 1, 2097152),
            ("max_history_messages", self.max_history_messages, 1, 4096),
        )
        for name, value, minimum, maximum in limits:
            if type(value) is not int or not minimum <= value <= maximum:
                raise NativeReplHold("invalid bounded " + name)


def _write_json(out: TextIO, value: dict[str, Any]) -> None:
    raw = json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    )
    out.write(raw + "\n")
    out.flush()


def _decode_message(raw: bytes, *, maximum: int) -> str:
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum + 1:
        raise NativeReplHold("invalid interactive input byte limit")
    if len(raw) > maximum:
        raise NativeReplHold("interactive message exceeds configured limit")
    try:
        text = raw.decode("utf-8", "strict").rstrip("\r\n")
    except UnicodeError as exc:
        raise NativeReplHold("interactive message must be UTF-8") from exc
    if chr(0) in text:
        raise NativeReplHold("NUL byte forbidden in interactive prompt")
    return text


class NativeJeevesRepl:
    """Operator-invoked, bounded chat loop backed by a NativeJeevesChat.

    Stop-on-error is essential: a model may have committed a response even if
    publication failed, or may have a pending unknown outcome. Continuing to
    generate after such a state is unsafe without an independent reconciliation.
    """

    def __init__(
        self,
        chat: NativeJeevesChat,
        *,
        limits: ReplLimits | None = None,
        source_fence: NativeSourceFence | None = None,
    ) -> None:
        if not isinstance(chat, NativeJeevesChat):
            raise NativeReplHold("Jeeves native chat must own the REPL")
        self.chat = chat
        if source_fence is not None and not isinstance(
            source_fence, NativeSourceFence,
        ):
            raise NativeReplHold("canonical live native source fence required")
        self.source_fence = source_fence
        if source_fence is not None:
            source_fence.assert_live(chat.worker)
        self.limits = limits or ReplLimits()
        if not isinstance(self.limits, ReplLimits):
            raise NativeReplHold("typed interactive limits required")
        if chat.worker.spine.limits.input_bytes < self.limits.max_input_bytes:
            self.limits = ReplLimits(
                max_turns=self.limits.max_turns,
                max_input_bytes=chat.worker.spine.limits.input_bytes,
                max_answer_bytes=min(
                    self.limits.max_answer_bytes,
                    chat.worker.spine.limits.response_bytes,
                ),
                max_history_messages=self.limits.max_history_messages,
            )
        self._turns = 0
        self._terminated = False

    def _publish(self, target: TextIO, payload: dict[str, Any]) -> None:
        # A native model can disappear or lose its capacity fence during a
        # SQLite history read or a committed inference. Never publish the
        # private result after its source lease or principal has changed.
        if self.source_fence is not None:
            self.source_fence.assert_live(self.chat.worker)
        _write_json(target, payload)

    def _status(self) -> dict[str, Any]:
        return {
            "schema": "jeeves.native_repl.status.v1",
            "session_id": self.chat.session_id,
            "tenant": self.chat.identity.tenant,
            "subject": self.chat.identity.subject,
            "model_sha256": self.chat.identity.model_sha256,
            "turns_this_process": self._turns,
            "remaining_turns": self.limits.max_turns - self._turns,
            "native_model_witnessed_here": self._turns > 0,
            "device_qualified": False,
            "release_certified": False,
        }

    def serve(self, source: BinaryIO, target: TextIO) -> int:
        if self._terminated:
            raise NativeReplHold("interactive loop already terminated")
        if not callable(getattr(source, "readline", None)):
            raise NativeReplHold("bounded binary input stream required")
        if not callable(getattr(target, "write", None)):
            raise NativeReplHold("JSON lines output stream required")
        self._publish(target, {"status": "jeeves-native-chat-ready", **self._status()})
        try:
            while self._turns < self.limits.max_turns:
                if self.source_fence is not None:
                    self.source_fence.assert_live(self.chat.worker)
                raw = source.readline(self.limits.max_input_bytes + 1)
                if raw == b"":
                    self._terminated = True
                    self._publish(target, {"status": "eof", **self._status()})
                    return 0
                message = _decode_message(raw, maximum=self.limits.max_input_bytes)
                if message == ":quit":
                    self._terminated = True
                    self._publish(target, {
                        "status": "session-preserved-for-resume",
                        **self._status(),
                    })
                    return 0
                if message == ":close":
                    self.chat.close()
                    self._terminated = True
                    self._publish(target, {"status": "session-closed", **self._status()})
                    return 0
                if message == ":status":
                    self._publish(target, {"status": "ready", **self._status()})
                    continue
                if message == ":help":
                    self._publish(target, {
                        "status": "help",
                        "commands": [":status", ":history", ":close", ":quit", ":help"],
                        "escape_prefix": "::",
                        **self._status(),
                    })
                    continue
                if message == ":history":
                    history = self.chat.history(
                        maximum_messages=self.limits.max_history_messages,
                    )
                    self._publish(target, {
                        "status": "explicit-history-export",
                        "history": list(history),
                        **self._status(),
                    })
                    continue
                if message.startswith("::"):
                    message = message[1:]
                if not message.strip():
                    raise NativeReplHold("interactive message cannot be empty")
                turn = self.chat.turn(message)
                self._turns += 1
                record = turn.to_record()
                if len(turn.text.encode("utf-8", "strict")) > self.limits.max_answer_bytes:
                    raise NativeReplHold("committed model response exceeds REPL output limit")
                self._publish(target, {
                    "status": "committed-native-chat-turn",
                    **record,
                })
            self._terminated = True
            self._publish(target, {
                "status": "bounded-turn-cap-reached-session-preserved",
                **self._status(),
            })
            return 0
        except (Exception, KeyboardInterrupt) as exc:
            self._terminated = True
            # Fail-closed. An uncertain native call may already have been
            # executed; never reissue it or emit private prompt text.
            _write_json(target, {
                "status": "held",
                "error_class": type(exc).__name__,
                "session_id": self.chat.session_id,
                "device_qualified": False,
                "release_certified": False,
            })
            return 2


__all__ = ["NativeReplHold", "ReplLimits", "NativeJeevesRepl"]
