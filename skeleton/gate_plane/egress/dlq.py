"""Dead-letter store for undeliverable callbacks.

Bounded in memory (oldest evicted first, eviction counted) with an optional
append-only JSON Lines sink so dead letters survive a restart. Entries
never contain secrets or signature headers — only the callback metadata,
the body digest/size (optionally the body itself, base64) and the attempt
history — so the file is safe to ship to an operator.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from skeleton.gate_plane.s2s.clock import Clock, system_clock

DEFAULT_CAPACITY = 10_000


@dataclass(frozen=True)
class DeadLetter:
    message_id: str
    subscription: str
    event_type: str
    url: str
    reason: str
    attempts: int
    first_attempt_at: float
    dead_at: float
    last_status: Optional[int] = None
    body_sha256: str = ""
    body_size: int = 0
    body_b64: Optional[str] = None
    history: Tuple[Dict[str, Any], ...] = ()

    def body(self) -> Optional[bytes]:
        return None if self.body_b64 is None else base64.b64decode(self.body_b64)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "subscription": self.subscription,
            "event_type": self.event_type,
            "url": self.url,
            "reason": self.reason,
            "attempts": self.attempts,
            "first_attempt_at": self.first_attempt_at,
            "dead_at": self.dead_at,
            "last_status": self.last_status,
            "body_sha256": self.body_sha256,
            "body_size": self.body_size,
            "body_b64": self.body_b64,
            "history": [dict(h) for h in self.history],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DeadLetter":
        return cls(
            message_id=str(d["message_id"]),
            subscription=str(d["subscription"]),
            event_type=str(d.get("event_type", "")),
            url=str(d["url"]),
            reason=str(d["reason"]),
            attempts=int(d.get("attempts", 0)),
            first_attempt_at=float(d.get("first_attempt_at", 0.0)),
            dead_at=float(d.get("dead_at", 0.0)),
            last_status=None if d.get("last_status") is None else int(d["last_status"]),
            body_sha256=str(d.get("body_sha256", "")),
            body_size=int(d.get("body_size", 0)),
            body_b64=d.get("body_b64"),
            history=tuple(dict(h) for h in d.get("history", []) or []),
        )


class DeadLetterQueue:
    def __init__(
        self,
        *,
        capacity: int = DEFAULT_CAPACITY,
        sink_path: Optional[str] = None,
        clock: Optional[Clock] = None,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = int(capacity)
        self.sink_path = sink_path
        self.clock: Clock = clock or system_clock()
        self._items: "OrderedDict[str, DeadLetter]" = OrderedDict()
        self._lock = threading.Lock()
        self.evicted = 0
        self.sink_errors = 0
        self._listeners: List[Callable[[DeadLetter], None]] = []

    def add_listener(self, fn: Callable[[DeadLetter], None]) -> None:
        self._listeners.append(fn)

    def put(self, letter: DeadLetter) -> None:
        with self._lock:
            self._items.pop(letter.message_id, None)
            self._items[letter.message_id] = letter
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)
                self.evicted += 1
        if self.sink_path:
            try:
                with open(self.sink_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"op": "put", **letter.as_dict()}, sort_keys=True) + "\n")
            except OSError:
                self.sink_errors += 1
        for fn in list(self._listeners):
            try:
                fn(letter)
            except Exception:  # noqa: BLE001
                pass

    def get(self, message_id: str) -> Optional[DeadLetter]:
        with self._lock:
            return self._items.get(message_id)

    def remove(self, message_id: str) -> Optional[DeadLetter]:
        with self._lock:
            letter = self._items.pop(message_id, None)
        if letter is not None and self.sink_path:
            try:
                with open(self.sink_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"op": "remove", "message_id": message_id}) + "\n")
            except OSError:
                self.sink_errors += 1
        return letter

    def list(self, *, subscription: Optional[str] = None, limit: Optional[int] = None) -> List[DeadLetter]:
        with self._lock:
            items = [d for d in self._items.values() if subscription is None or d.subscription == subscription]
        return items if limit is None else items[: max(0, int(limit))]

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __iter__(self) -> Iterator[DeadLetter]:
        return iter(self.list())

    def load(self) -> int:
        """Rebuild in-memory state from ``sink_path`` (put/remove log). Returns live count."""
        if not self.sink_path or not os.path.exists(self.sink_path):
            return 0
        rebuilt: "OrderedDict[str, DeadLetter]" = OrderedDict()
        with open(self.sink_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("op") == "remove":
                        rebuilt.pop(str(rec["message_id"]), None)
                    else:
                        rec.pop("op", None)
                        letter = DeadLetter.from_dict(rec)
                        rebuilt.pop(letter.message_id, None)
                        rebuilt[letter.message_id] = letter
                except (ValueError, KeyError, TypeError):
                    self.sink_errors += 1
        while len(rebuilt) > self.capacity:
            rebuilt.popitem(last=False)
        with self._lock:
            self._items = rebuilt
            return len(self._items)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            by_reason: Dict[str, int] = {}
            for d in self._items.values():
                by_reason[d.reason] = by_reason.get(d.reason, 0) + 1
            return {
                "size": len(self._items),
                "capacity": self.capacity,
                "evicted": self.evicted,
                "sink_errors": self.sink_errors,
                "by_reason": dict(sorted(by_reason.items())),
            }


__all__ = ["DeadLetter", "DeadLetterQueue"]
