"""At-least-once inter-agent message bus with per-conversation ordering.

Delivery model
--------------

* **Publish** validates the envelope, suppresses duplicates through a
  :class:`~skeleton.gate_plane.agent_edge.dedup.DedupWindow` (keyed by
  :attr:`Envelope.dedup_key`) and assigns a bus-owned, gap-free
  per-conversation ``sequence``.
* **Pull** leases messages to a consumer. Within one conversation only the
  *head* message is ever eligible, and only while no other message of that
  conversation is leased, so a consumer observes each conversation strictly
  in sequence order even across redeliveries. Different conversations are
  independent and are served by ``(priority, enqueue order)``.
* **Ack** removes the head and marks the dedup key ``done`` so a late
  duplicate publish is still suppressed after processing.
* **Nack** schedules a redelivery with capped exponential backoff, or
  dead-letters the message when ``retry=False`` / ``poison=True``.
* A lease that is neither acked nor nacked expires; the message becomes
  eligible again (at-least-once). Every lease counts as an attempt; once
  ``envelope.max_attempts`` attempts are spent the message is dead-lettered
  with :attr:`DeadLetterReason.MAX_ATTEMPTS`.
* Messages whose TTL elapses before they are acked are dead-lettered with
  :attr:`DeadLetterReason.TTL_EXPIRED`; the conversation then advances.

The bus is a pure, thread-safe, in-process library driven by explicit
``now`` values (or an injectable clock); it has no host side effects and is
safe to run under seeded chaos.
"""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Tuple

from skeleton.gate_plane.agent_edge.dedup import DedupWindow
from skeleton.gate_plane.agent_edge.dlq import DeadLetter, DeadLetterQueue, DeadLetterReason
from skeleton.gate_plane.agent_edge.envelope import Envelope, EnvelopeError, validate_agent_id
from skeleton.gate_plane.s2s.clock import Clock, system_clock

DEFAULT_LEASE_S = 30.0
MAX_LEASE_S = 900.0
DEFAULT_BACKOFF_BASE_S = 0.5
DEFAULT_BACKOFF_CAP_S = 60.0
DEFAULT_MAX_PENDING_PER_AGENT = 50_000
MAX_PULL_BATCH = 256

STATE_PENDING = "pending"
STATE_DONE = "done"
STATE_DEAD = "dead"


class BusError(Exception):
    """Base class for bus errors."""


class BusFull(BusError):
    """The recipient's pending queue is at capacity."""

    def __init__(self, recipient: str, capacity: int) -> None:
        super().__init__(f"queue for {recipient!r} is full ({capacity})")
        self.recipient = recipient
        self.capacity = capacity


class UnknownLease(BusError):
    """Ack/nack for a lease the bus does not know (never issued or already settled)."""


class StaleLease(BusError):
    """Ack/nack for a lease that expired and was re-issued to another consumer."""


class PublishStatus(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    ALREADY_PROCESSED = "already_processed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class PublishResult:
    status: PublishStatus
    message_id: str
    conversation_id: str
    sequence: Optional[int] = None

    @property
    def accepted(self) -> bool:
        return self.status is PublishStatus.ACCEPTED

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class Delivery:
    """A leased message handed to a consumer."""

    envelope: Envelope
    lease_id: str
    attempt: int
    lease_expires_at: float

    @property
    def redelivery(self) -> bool:
        return self.attempt > 1

    def as_dict(self) -> Dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "attempt": self.attempt,
            "lease_expires_at": self.lease_expires_at,
            "redelivery": self.redelivery,
            "envelope": self.envelope.to_wire(),
        }


@dataclass
class _Slot:
    envelope: Envelope
    enqueue_seq: int
    attempts: int = 0
    not_before: float = 0.0
    lease_id: Optional[str] = None
    lease_expires_at: float = 0.0
    last_error: Optional[str] = None

    def leased(self, now: float) -> bool:
        return self.lease_id is not None and self.lease_expires_at > now


@dataclass
class _Conversation:
    conversation_id: str
    queue: Deque[_Slot] = field(default_factory=deque)


@dataclass
class _Mailbox:
    agent_id: str
    conversations: "OrderedDict[str, _Conversation]" = field(default_factory=OrderedDict)
    pending: int = 0


def backoff_delay(attempt: int, *, base_s: float = DEFAULT_BACKOFF_BASE_S, cap_s: float = DEFAULT_BACKOFF_CAP_S) -> float:
    """Capped exponential backoff: ``base * 2**(attempt-1)`` bounded by ``cap``."""
    if attempt < 1:
        return 0.0
    return float(min(cap_s, base_s * (2 ** min(attempt - 1, 30))))


BusListener = Callable[[str, Dict[str, Any]], None]


class AgentBus:
    """In-process at-least-once bus; see module docstring for semantics."""

    def __init__(
        self,
        *,
        dedup: Optional[DedupWindow] = None,
        dlq: Optional[DeadLetterQueue] = None,
        clock: Optional[Clock] = None,
        default_lease_s: float = DEFAULT_LEASE_S,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        backoff_cap_s: float = DEFAULT_BACKOFF_CAP_S,
        max_pending_per_agent: int = DEFAULT_MAX_PENDING_PER_AGENT,
        lease_id_factory: Optional[Callable[[], str]] = None,
    ) -> None:
        if not 0 < default_lease_s <= MAX_LEASE_S:
            raise ValueError(f"default_lease_s must be within (0, {MAX_LEASE_S}]")
        if backoff_base_s < 0 or backoff_cap_s < backoff_base_s:
            raise ValueError("need 0 <= backoff_base_s <= backoff_cap_s")
        if max_pending_per_agent < 1:
            raise ValueError("max_pending_per_agent must be >= 1")
        self.dedup = dedup if dedup is not None else DedupWindow()
        self.dlq = dlq if dlq is not None else DeadLetterQueue()
        self.clock: Clock = clock if clock is not None else system_clock()
        self.default_lease_s = float(default_lease_s)
        self.backoff_base_s = float(backoff_base_s)
        self.backoff_cap_s = float(backoff_cap_s)
        self.max_pending_per_agent = int(max_pending_per_agent)
        self._lease_id_factory = lease_id_factory
        self._lock = threading.RLock()
        self._mailboxes: Dict[str, _Mailbox] = {}
        self._next_seq: Dict[str, int] = {}
        self._leases: Dict[str, Tuple[str, str, str]] = {}  # lease_id -> (recipient, conversation, message_id)
        self._enqueue_counter = 0
        self._listeners: List[BusListener] = []
        self._counts: Dict[str, int] = {}

    # -- plumbing ---------------------------------------------------------------
    def _now(self, now: Optional[float]) -> float:
        return float(self.clock.now() if now is None else now)

    def add_listener(self, listener: BusListener) -> None:
        self._listeners.append(listener)

    def _emit(self, event: str, **data: Any) -> None:
        self._counts[event] = self._counts.get(event, 0) + 1
        for listener in list(self._listeners):
            try:
                listener(event, dict(data))
            except Exception:  # noqa: BLE001 - observers never change delivery
                pass

    def _new_lease_id(self) -> str:
        if self._lease_id_factory is not None:
            return str(self._lease_id_factory())
        return f"lease-{secrets.token_hex(10)}"

    def _mailbox(self, agent_id: str) -> _Mailbox:
        box = self._mailboxes.get(agent_id)
        if box is None:
            box = _Mailbox(agent_id)
            self._mailboxes[agent_id] = box
        return box

    # -- publish ----------------------------------------------------------------
    def publish(self, envelope: Envelope, *, now: Optional[float] = None) -> PublishResult:
        if not isinstance(envelope, Envelope):
            raise EnvelopeError("publish expects an Envelope")
        t = self._now(now)
        with self._lock:
            if envelope.expired(t):
                self._emit("expired_on_publish", message_id=envelope.message_id)
                return PublishResult(PublishStatus.EXPIRED, envelope.message_id, envelope.conversation_id)
            key = envelope.dedup_key
            state = self.dedup.seen(key, t)
            if state == STATE_DONE:
                self._emit("duplicate_processed", message_id=envelope.message_id)
                return PublishResult(PublishStatus.ALREADY_PROCESSED, envelope.message_id, envelope.conversation_id)
            if state is not None:
                self._emit("duplicate", message_id=envelope.message_id)
                return PublishResult(PublishStatus.DUPLICATE, envelope.message_id, envelope.conversation_id)
            box = self._mailbox(envelope.recipient)
            if box.pending >= self.max_pending_per_agent:
                self._emit("rejected_full", recipient=envelope.recipient)
                raise BusFull(envelope.recipient, self.max_pending_per_agent)
            self.dedup.remember(key, t, STATE_PENDING)
            seq_key = f"{envelope.recipient}\x00{envelope.conversation_id}"
            seq = self._next_seq.get(seq_key, 0) + 1
            self._next_seq[seq_key] = seq
            stored = envelope.with_sequence(seq)
            conv = box.conversations.get(envelope.conversation_id)
            if conv is None:
                conv = _Conversation(envelope.conversation_id)
                box.conversations[envelope.conversation_id] = conv
            self._enqueue_counter += 1
            conv.queue.append(_Slot(stored, self._enqueue_counter))
            box.pending += 1
            self._emit("published", message_id=stored.message_id, recipient=stored.recipient, sequence=seq)
            return PublishResult(PublishStatus.ACCEPTED, stored.message_id, stored.conversation_id, seq)

    def publish_many(self, envelopes: Iterable[Envelope], *, now: Optional[float] = None) -> List[PublishResult]:
        return [self.publish(e, now=now) for e in envelopes]

    # -- dead-lettering ---------------------------------------------------------
    def _dead_letter(self, box: _Mailbox, conv: _Conversation, slot: _Slot, reason: DeadLetterReason, t: float) -> None:
        conv.queue.popleft()
        box.pending -= 1
        if slot.lease_id is not None:
            self._leases.pop(slot.lease_id, None)
        self.dlq.put(DeadLetter(slot.envelope, reason, slot.attempts, t, slot.last_error))
        self.dedup.mark(slot.envelope.dedup_key, t, STATE_DEAD)
        self._emit("dead_lettered", message_id=slot.envelope.message_id, reason=reason.value)
        if not conv.queue:
            box.conversations.pop(conv.conversation_id, None)

    def _settle_head(self, box: _Mailbox, conv: _Conversation, t: float) -> Optional[_Slot]:
        """Dead-letter expired / exhausted heads; return the live head (or None)."""
        while conv.queue:
            slot = conv.queue[0]
            if slot.leased(t):
                return slot
            if slot.envelope.expired(t):
                self._dead_letter(box, conv, slot, DeadLetterReason.TTL_EXPIRED, t)
                continue
            if slot.lease_id is not None:
                # lease lapsed without settlement -> redelivery candidate
                self._leases.pop(slot.lease_id, None)
                slot.lease_id = None
                slot.last_error = slot.last_error or "lease_expired"
                self._emit("lease_expired", message_id=slot.envelope.message_id, attempt=slot.attempts)
                slot.not_before = max(slot.not_before, t)
            if slot.attempts >= slot.envelope.max_attempts:
                self._dead_letter(box, conv, slot, DeadLetterReason.MAX_ATTEMPTS, t)
                continue
            return slot
        return None

    # -- pull / ack / nack -------------------------------------------------------
    def pull(
        self,
        agent_id: str,
        *,
        max_messages: int = 1,
        lease_s: Optional[float] = None,
        now: Optional[float] = None,
        topics: Optional[Iterable[str]] = None,
    ) -> List[Delivery]:
        validate_agent_id(agent_id)
        if not 1 <= int(max_messages) <= MAX_PULL_BATCH:
            raise ValueError(f"max_messages must be within 1..{MAX_PULL_BATCH}")
        lease = self.default_lease_s if lease_s is None else float(lease_s)
        if not 0 < lease <= MAX_LEASE_S:
            raise ValueError(f"lease_s must be within (0, {MAX_LEASE_S}]")
        topic_filter = None if topics is None else frozenset(topics)
        t = self._now(now)
        with self._lock:
            box = self._mailboxes.get(agent_id)
            if box is None:
                return []
            candidates: List[Tuple[int, int, _Conversation, _Slot]] = []
            for conv in list(box.conversations.values()):
                head = self._settle_head(box, conv, t)
                if head is None or head.leased(t) or head.not_before > t:
                    continue
                if topic_filter is not None and head.envelope.topic not in topic_filter:
                    continue
                candidates.append((head.envelope.priority, head.enqueue_seq, conv, head))
            candidates.sort(key=lambda c: (c[0], c[1]))
            out: List[Delivery] = []
            for _prio, _seq, _conv, slot in candidates[: int(max_messages)]:
                slot.attempts += 1
                slot.lease_id = self._new_lease_id()
                slot.lease_expires_at = t + lease
                self._leases[slot.lease_id] = (agent_id, slot.envelope.conversation_id, slot.envelope.message_id)
                out.append(Delivery(slot.envelope, slot.lease_id, slot.attempts, slot.lease_expires_at))
                self._emit(
                    "delivered",
                    message_id=slot.envelope.message_id,
                    attempt=slot.attempts,
                    sequence=slot.envelope.sequence,
                )
            return out

    def _locate(self, lease_id: str, t: float) -> Tuple[_Mailbox, _Conversation, _Slot]:
        ref = self._leases.get(lease_id)
        if ref is None:
            raise UnknownLease(lease_id)
        recipient, conv_id, message_id = ref
        box = self._mailboxes.get(recipient)
        conv = None if box is None else box.conversations.get(conv_id)
        if box is None or conv is None or not conv.queue or conv.queue[0].envelope.message_id != message_id:
            self._leases.pop(lease_id, None)
            raise UnknownLease(lease_id)
        slot = conv.queue[0]
        if slot.lease_id != lease_id:
            self._leases.pop(lease_id, None)
            raise StaleLease(lease_id)
        if slot.lease_expires_at <= t:
            raise StaleLease(lease_id)
        return box, conv, slot

    def lease_owner(self, lease_id: str) -> Optional[str]:
        """Recipient agent a lease was issued to (``None`` when unknown/settled)."""
        with self._lock:
            ref = self._leases.get(lease_id)
            return None if ref is None else ref[0]

    def ack(self, lease_id: str, *, now: Optional[float] = None) -> Envelope:
        t = self._now(now)
        with self._lock:
            box, conv, slot = self._locate(lease_id, t)
            conv.queue.popleft()
            box.pending -= 1
            self._leases.pop(lease_id, None)
            if not conv.queue:
                box.conversations.pop(conv.conversation_id, None)
            self.dedup.mark(slot.envelope.dedup_key, t, STATE_DONE)
            self._emit("acked", message_id=slot.envelope.message_id, attempt=slot.attempts)
            return slot.envelope

    def nack(
        self,
        lease_id: str,
        *,
        error: str = "",
        retry: bool = True,
        poison: bool = False,
        delay_s: Optional[float] = None,
        now: Optional[float] = None,
    ) -> Optional[DeadLetter]:
        """Return the message for redelivery, or dead-letter it.

        Returns the :class:`DeadLetter` when the message left the queue.
        """
        t = self._now(now)
        with self._lock:
            box, conv, slot = self._locate(lease_id, t)
            self._leases.pop(lease_id, None)
            slot.lease_id = None
            slot.last_error = (error or "nack")[:512]
            if poison or not retry:
                reason = DeadLetterReason.POISON if poison else DeadLetterReason.REJECTED
                self._dead_letter(box, conv, slot, reason, t)
                return self.dlq.get(slot.envelope.message_id)
            if slot.attempts >= slot.envelope.max_attempts:
                self._dead_letter(box, conv, slot, DeadLetterReason.MAX_ATTEMPTS, t)
                return self.dlq.get(slot.envelope.message_id)
            wait = backoff_delay(slot.attempts, base_s=self.backoff_base_s, cap_s=self.backoff_cap_s)
            if delay_s is not None:
                wait = max(0.0, min(float(delay_s), self.backoff_cap_s))
            slot.not_before = t + wait
            self._emit("nacked", message_id=slot.envelope.message_id, attempt=slot.attempts, delay_s=wait)
            return None

    def extend(self, lease_id: str, *, lease_s: Optional[float] = None, now: Optional[float] = None) -> float:
        """Extend a live lease (heartbeat); returns the new expiry."""
        t = self._now(now)
        lease = self.default_lease_s if lease_s is None else float(lease_s)
        if not 0 < lease <= MAX_LEASE_S:
            raise ValueError(f"lease_s must be within (0, {MAX_LEASE_S}]")
        with self._lock:
            _box, _conv, slot = self._locate(lease_id, t)
            slot.lease_expires_at = t + lease
            return slot.lease_expires_at

    def reject_undeliverable(self, envelope: Envelope, reason: DeadLetterReason, *, error: str = "", now: Optional[float] = None) -> DeadLetter:
        """Dead-letter a message that never entered a mailbox (no route, unauthorized)."""
        t = self._now(now)
        letter = DeadLetter(envelope, reason, 0, t, error[:512] or None)
        with self._lock:
            self.dlq.put(letter)
            self._emit("dead_lettered", message_id=envelope.message_id, reason=reason.value)
        return letter

    # -- DLQ replay ---------------------------------------------------------------
    def replay(self, message_id: str, *, now: Optional[float] = None, reset_ttl: bool = True) -> PublishResult:
        """Move a dead letter back onto the bus (same message id, fresh attempts)."""
        t = self._now(now)
        with self._lock:
            letter = self.dlq.take(message_id)
            if letter is None:
                raise KeyError(message_id)
            env = letter.envelope
            if reset_ttl:
                from dataclasses import replace

                env = replace(env, created_at=t)
            self.dedup.forget(env.dedup_key)
            result = self.publish(env, now=t)
            if not result.accepted:
                self.dlq.put(letter)
            else:
                self._emit("replayed", message_id=message_id)
            return result

    # -- dispatch helper -----------------------------------------------------------
    def dispatch(
        self,
        agent_id: str,
        handler: Callable[[Envelope], Any],
        *,
        max_messages: int = 32,
        now: Optional[float] = None,
        lease_s: Optional[float] = None,
    ) -> Dict[str, int]:
        """Pull and run ``handler`` for each delivery; ack on return, nack on raise.

        A handler raising :class:`PoisonMessage` dead-letters immediately.
        """
        stats = {"delivered": 0, "acked": 0, "nacked": 0, "dead": 0}
        t = self._now(now)
        for delivery in self.pull(agent_id, max_messages=max_messages, now=t, lease_s=lease_s):
            stats["delivered"] += 1
            try:
                handler(delivery.envelope)
            except PoisonMessage as exc:
                self.nack(delivery.lease_id, error=str(exc) or "poison", poison=True, now=t)
                stats["dead"] += 1
                continue
            except Exception as exc:  # noqa: BLE001 - handler failures become nacks
                dead = self.nack(delivery.lease_id, error=f"{type(exc).__name__}: {exc}", now=t)
                stats["dead" if dead is not None else "nacked"] += 1
                continue
            self.ack(delivery.lease_id, now=t)
            stats["acked"] += 1
        return stats

    # -- introspection ---------------------------------------------------------------
    def depth(self, agent_id: Optional[str] = None) -> int:
        with self._lock:
            if agent_id is not None:
                box = self._mailboxes.get(agent_id)
                return 0 if box is None else box.pending
            return sum(b.pending for b in self._mailboxes.values())

    def in_flight(self, agent_id: Optional[str] = None, *, now: Optional[float] = None) -> int:
        t = self._now(now)
        with self._lock:
            n = 0
            for box in self._mailboxes.values():
                if agent_id is not None and box.agent_id != agent_id:
                    continue
                for conv in box.conversations.values():
                    if conv.queue and conv.queue[0].leased(t):
                        n += 1
            return n

    def conversations(self, agent_id: str) -> List[str]:
        with self._lock:
            box = self._mailboxes.get(agent_id)
            return [] if box is None else list(box.conversations)

    def peek(self, agent_id: str, conversation_id: str) -> List[Envelope]:
        with self._lock:
            box = self._mailboxes.get(agent_id)
            conv = None if box is None else box.conversations.get(conversation_id)
            return [] if conv is None else [s.envelope for s in conv.queue]

    def agents(self) -> List[str]:
        with self._lock:
            return sorted(a for a, b in self._mailboxes.items() if b.pending)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "pending": sum(b.pending for b in self._mailboxes.values()),
                "mailboxes": {a: b.pending for a, b in sorted(self._mailboxes.items()) if b.pending},
                "leases": len(self._leases),
                "events": dict(self._counts),
                "dedup": self.dedup.stats(),
                "dlq": self.dlq.stats(),
            }


class PoisonMessage(Exception):
    """Raise from a handler to dead-letter a message without retries."""


__all__ = [
    "AgentBus",
    "BusError",
    "BusFull",
    "DEFAULT_LEASE_S",
    "Delivery",
    "MAX_LEASE_S",
    "MAX_PULL_BATCH",
    "PoisonMessage",
    "PublishResult",
    "PublishStatus",
    "StaleLease",
    "UnknownLease",
    "backoff_delay",
]
