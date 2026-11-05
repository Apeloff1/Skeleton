"""One installed GGUF model, many principal-bound Jeeves conversations.

No HTTP listener, hosted model, implicit tool use, or separate state owner.
Input is one UTF-8 message per line; transcript identity and committed answers
are produced by the existing native SQLite authority. An uncertain native
call stops the interactive session without automatically issuing a retry.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import threading
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
    max_result_frame_bytes: int = 262144
    max_total_output_bytes: int = 8388608

    def __post_init__(self):
        limits = (
            ("max_turns", self.max_turns, 1, 4096),
            ("max_input_bytes", self.max_input_bytes, 1, 1048576),
            ("max_answer_bytes", self.max_answer_bytes, 1, 2097152),
            ("max_history_messages", self.max_history_messages, 1, 4096),
            ("max_result_frame_bytes", self.max_result_frame_bytes, 1, 4194304),
            ("max_total_output_bytes", self.max_total_output_bytes, 1, 67108864),
        )
        for name, value, minimum, maximum in limits:
            if type(value) is not int or not minimum <= value <= maximum:
                raise NativeReplHold("invalid bounded " + name)
        if self.max_total_output_bytes < self.max_result_frame_bytes:
            raise NativeReplHold(
                "REPL total output must cover one complete result frame"
            )


def _write_json(out: TextIO, value: dict[str, Any]) -> None:
    raw = json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    )
    out.write(raw + "\n")
    out.flush()


def _decode_message(raw: bytes, *, maximum: int) -> str:
    """Remove exactly one wire record delimiter, never prompt whitespace.

    The maximum counts UTF-8 task bytes, not line framing bytes. Accept
    bounded LF, CRLF or final EOF records; do not strip an extra terminal
    CR from a deliberately supplied prompt or silently truncate Unicode.
    """
    if (type(maximum) is not int or not 1 <= maximum <= 1048576
            or type(raw) is not bytes or not raw
            or len(raw) > maximum + 2):
        raise NativeReplHold("invalid interactive input byte limit")
    payload = raw
    if payload.endswith(b"\n"):
        payload = payload[:-1]
        if payload.endswith(b"\r"):
            payload = payload[:-1]
    if b"\n" in payload:
        raise NativeReplHold("one prompt per interactive input record")
    if not 1 <= len(payload) <= maximum:
        raise NativeReplHold("interactive message exceeds configured limit")
    try:
        text = payload.decode("utf-8", "strict")
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
                max_result_frame_bytes=self.limits.max_result_frame_bytes,
                max_total_output_bytes=self.limits.max_total_output_bytes,
            )
        self._turns = 0
        self._terminated = False
        self._output_bytes = 0
        self._uncertain_output = False
        # The entire interactive stdin stream has one process-local owner.
        # A second serve() must fail before reading private input while the
        # first caller blocks in readline or native inference.
        self._state_lock = threading.RLock()
        self._serving = False
        self._serving_thread = None

    def _publish(self, target: TextIO, payload: dict[str, Any]) -> None:
        # A native model can disappear or lose its capacity fence during a
        # SQLite history read or a committed inference. Never publish the
        # private result after its source lease or principal has changed.
        raw = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ) + "\n"
        amount = len(raw.encode("utf-8", "strict"))
        if amount > self.limits.max_result_frame_bytes:
            raise NativeReplHold("REPL result exceeds private frame bound")
        if self._output_bytes + amount > self.limits.max_total_output_bytes:
            raise NativeReplHold("REPL session disclosure budget exhausted")
        if self.source_fence is not None:
            self.source_fence.assert_live(self.chat.worker)
        # Charge bytes before attempting output. Unknown partial writes are
        # terminal and cannot refund quota or generate another native effect.
        self._output_bytes += amount
        self._uncertain_output = True
        written = target.write(raw)
        if type(written) is not int or written != len(raw):
            raise NativeReplHold("REPL output stream accepted incomplete frame")
        if callable(getattr(target, "flush", None)):
            target.flush()
        self._uncertain_output = False

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
        with self._state_lock:
            if self._terminated or self._serving:
                raise NativeReplHold("interactive loop already active or terminated")
            if not callable(getattr(source, "readline", None)):
                raise NativeReplHold("bounded binary input stream required")
            if not callable(getattr(target, "write", None)):
                raise NativeReplHold("JSON lines output stream required")
            self._serving = True
            self._serving_thread = threading.get_ident()
        try:
            return self._serve_exclusive_stream(source, target)
        finally:
            with self._state_lock:
                self._serving = False
                self._serving_thread = None
                self._terminated = True

    def _serve_exclusive_stream(self, source: BinaryIO, target: TextIO) -> int:
        # The first live-source check is an activation/authorization fence.
        # Preserve the existing public behavior: failures before the ready
        # frame propagate to the CLI; they are not converted into a healthy
        # REPL session or a misleading output-status record.
        try:
            self._publish(target, {"status": "jeeves-native-chat-ready", **self._status()})
        except BaseException:
            self._terminated = True
            raise
        try:
            while self._turns < self.limits.max_turns:
                if self.source_fence is not None:
                    self.source_fence.assert_live(self.chat.worker)
                raw = source.readline(self.limits.max_input_bytes + 3)
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
                    # Bound transcript materialization separately from
                    # the full output frame and cumulative disclosure quota.
                    remaining = max(
                        1, self.limits.max_total_output_bytes-self._output_bytes
                    )
                    history = self.chat.history(
                        maximum_messages=self.limits.max_history_messages,
                        maximum_total_bytes=min(
                            remaining, self.limits.max_result_frame_bytes,
                        ),
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
            if not self._uncertain_output:
                # A broken writer may have emitted a truncated private line.
                # Never append JSON to such a partial line or claim success.
                _write_json(target, {
                    "status": "held",
                    "error_class": type(exc).__name__,
                    "session_id": self.chat.session_id,
                    "device_qualified": False,
                    "release_certified": False,
                })
            return 2


__all__ = ["NativeReplHold", "ReplLimits", "NativeJeevesRepl"]
