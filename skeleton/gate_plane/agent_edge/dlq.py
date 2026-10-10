"""Dead-letter queue for undeliverable inter-agent messages."""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from skeleton.gate_plane.agent_edge.envelope import Envelope


class DeadLetterReason(str, Enum):
    TTL_EXPIRED = "ttl_expired"
    MAX_ATTEMPTS = "max_attempts"
    REJECTED = "rejected"
    NO_ROUTE = "no_route"
    UNAUTHORIZED = "unauthorized"
    POISON = "poison"


@dataclass(frozen=True)
class DeadLetter:
    envelope: Envelope
    reason: DeadLetterReason
    attempts: int
    dead_at: float
    last_error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.envelope.message_id,
            "conversation_id": self.envelope.conversation_id,
            "correlation_id": self.envelope.correlation_id,
            "sender": self.envelope.sender,
            "recipient": self.envelope.recipient,
            "topic": self.envelope.topic,
            "sequence": self.envelope.sequence,
            "reason": self.reason.value,
            "attempts": self.attempts,
            "dead_at": self.dead_at,
            "last_error": self.last_error,
        }


class DeadLetterQueue:
    """Bounded FIFO of dead letters keyed by message id.

    When full, the oldest letter is dropped and counted in :attr:`dropped`
    (never silently: operators alert on it).
    """

    def __init__(self, *, capacity: int = 10_000) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = int(capacity)
        self._letters: "OrderedDict[str, DeadLetter]" = OrderedDict()
        self._lock = threading.Lock()
        self.dropped = 0
        self._by_reason: Dict[str, int] = {}

    def put(self, letter: DeadLetter) -> None:
        with self._lock:
            self._letters.pop(letter.envelope.message_id, None)
            self._letters[letter.envelope.message_id] = letter
            self._by_reason[letter.reason.value] = self._by_reason.get(letter.reason.value, 0) + 1
            while len(self._letters) > self.capacity:
                self._letters.popitem(last=False)
                self.dropped += 1

    def get(self, message_id: str) -> Optional[DeadLetter]:
        with self._lock:
            return self._letters.get(message_id)

    def take(self, message_id: str) -> Optional[DeadLetter]:
        with self._lock:
            return self._letters.pop(message_id, None)

    def list(
        self,
        *,
        recipient: Optional[str] = None,
        reason: Optional[DeadLetterReason] = None,
        limit: int = 100,
    ) -> List[DeadLetter]:
        with self._lock:
            out = [
                dl
                for dl in self._letters.values()
                if (recipient is None or dl.envelope.recipient == recipient)
                and (reason is None or dl.reason is reason)
            ]
        return out[: max(0, int(limit))]

    def purge(self, *, older_than: Optional[float] = None) -> int:
        with self._lock:
            if older_than is None:
                n = len(self._letters)
                self._letters.clear()
                return n
            stale = [k for k, v in self._letters.items() if v.dead_at < older_than]
            for k in stale:
                del self._letters[k]
            return len(stale)

    def __len__(self) -> int:
        with self._lock:
            return len(self._letters)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"size": len(self._letters), "dropped": self.dropped, "by_reason": dict(self._by_reason)}


__all__ = ["DeadLetter", "DeadLetterQueue", "DeadLetterReason"]
