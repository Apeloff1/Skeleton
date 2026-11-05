"""Source-bound, owner-scoped operations over the canonical native supervisor.

No synthetic successful generation, extra database or retry lane exists.
Native turn output is never published unless independent read-only SQLite
replay proves the same exact committed text and digest.
"""
from __future__ import annotations

import secrets
import threading

from .contracts import refuse
from .identity import ActiveModel
from .inputs import normalize
from .operations import schema
from .result_protocol import verify_turn_receipt


class LaptopDispatcher:
    """Guard a fixed active principal across all native API operations."""

    def __init__(self, worker):
        if worker is None or not hasattr(worker, "spine") or not hasattr(worker, "turn"):
            refuse("production supervisor required")
        self.worker = worker
        self.active = ActiveModel.from_supervisor(worker)
        self.limits = worker.spine.limits
        # The same loopback server serves concurrent authenticated clients.
        # One dispatcher permits only one in-flight read OR native effect so a
        # close, replay, history or outbox ack cannot race an active turn.
        self._flight = threading.Lock()

    def _assert_current(self) -> None:
        """Deny stale model, tokenizer, tenant or subject before private IO."""
        try:
            observed = ActiveModel.from_supervisor(self.worker)
        except (AttributeError, ValueError) as exc:
            refuse("native supervisor principal unavailable")
        if observed != self.active:
            refuse("native supervisor identity changed after binding")

    def _read_committed(self, data: dict[str, object]) -> dict[str, object] | None:
        """Only the canonical durable replay can prove a committed answer."""
        saved = self.worker.spine.replay(
            data["session_id"], data["request_id"], data["prompt"],
            seed=data.get("seed", 0),
            temperature=data.get("temperature", 0.8),
        )
        if saved is None:
            return None
        verified = verify_turn_receipt(
            saved,
            model_sha256=self.active.model_sha256,
            tokenizer_sha256=self.active.tokenizer_sha256,
        )
        if verified["replayed"] is not True:
            refuse("SQLite replay must be explicitly marked replayed")
        return verified

    def dispatch(self, operation, payload):
        """Single-flight admission for the actual shared laptop HTTP dispatcher.

        Reject concurrency instead of silently queuing native generations,
        replay reads or SQLite mutations behind an unbounded request backlog.
        The lock is released even when generation fails or is uncertain; the
        canonical ExecutionSpine still owns its persistent pending fence.
        """
        data = normalize(operation, payload, self.limits)
        if not self._flight.acquire(blocking=False):
            refuse("native dispatcher already has an active request")
        try:
            return self._dispatch_exclusive(operation, data)
        finally:
            self._flight.release()

    def _dispatch_exclusive(self, operation, data):
        """Only the installed active principal may cross the native boundary."""
        self._assert_current()
        if operation == "create":
            session = "s_" + secrets.token_hex(16)
            allocated = self.worker.spine.create(session)
            if allocated != session:
                refuse("native SQLite session allocation disagreed")
            self._assert_current()
            return {
                "session_id": session,
                "model_sha256": self.active.model_sha256,
            }
        if operation == "turn":
            produced = self.worker.turn(
                data["session_id"], data["request_id"], data["prompt"],
                seed=data.get("seed", 0),
                temperature=data.get("temperature", 0.8),
            )
            # Even a signed, schema-valid worker reply is not sufficient:
            # it may have failed before the transactional SQLite commit.
            checked = verify_turn_receipt(
                produced,
                model_sha256=self.active.model_sha256,
                tokenizer_sha256=self.active.tokenizer_sha256,
            )
            committed = self._read_committed(data)
            if committed is None:
                refuse("native generation is missing a committed SQLite replay")
            for name in (
                "text", "output_sha256", "model_sha256", "tokenizer_sha256",
                "prompt_tokens", "generated_tokens",
            ):
                if checked[name] != committed[name]:
                    refuse("native result differs from committed SQLite replay")
            self._assert_current()
            return {"receipt": checked}
        if operation == "history":
            result = self.worker.spine.history(data["session_id"])
            if type(result) not in (tuple, list):
                refuse("invalid authoritative transcript")
            self._assert_current()
            return {"session_id": data["session_id"], "messages": list(result)}
        if operation == "replay":
            result = self._read_committed(data)
            self._assert_current()
            return {"replay": result, "found": result is not None}
        if operation == "close":
            result = self.worker.spine.close(data["session_id"])
            if type(result) is not bool:
                refuse("invalid native session closure")
            self._assert_current()
            return {"closed": result}
        if operation == "status":
            result = self.worker.status()
            self._assert_current()
            return {
                "status": result,
                "model_sha256": self.active.model_sha256,
            }
        if operation == "doctor":
            result = self.worker.spine.health()
            self._assert_current()
            return {"doctor": result, "release_certified": False}
        if operation == "identity":
            return {
                "identity": self.active.to_record(),
                "release_certified": False,
            }
        if operation == "outbox_pending":
            events = list(
                self.worker.spine.pending_events(limit=data.get("limit", 16))
            )
            self._assert_current()
            return {"events": events}
        if operation == "outbox_ack":
            acknowledged = self.worker.spine.acknowledge_event(
                data["event_key"], data["event_sha256"]
            )
            if type(acknowledged) is not bool:
                refuse("invalid durable outbox acknowledgment")
            self._assert_current()
            return {"acknowledged": acknowledged}
        refuse("unreachable unapproved operation")

    def protocol(self):
        return schema()
