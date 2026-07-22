from __future__ import annotations
"""
All-rooms logging with mandatory twins.
Every room event is mirrored unfiltered; originals may summarize.
"""

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from gameforge.exocortex.zaibatsu.studio import STUDIO_ROOMS
try:
    from gameforge.rooms.full_room_registry import all_rooms as _all_rooms
except Exception:
    def _all_rooms():
        return dict(STUDIO_ROOMS)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RoomLogEntry:
    entry_id: str
    room_id: str
    event: str
    payload: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


class RoomLogBook:
    """Per-room append-only log + twin mirror callback."""

    def __init__(self, room_id: str, user_id: str, twin_write=None):
        self.room_id = room_id
        self.user_id = user_id
        self.twin_write = twin_write
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.path = base / "room_logs" / user_id / f"{room_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cache: List[Dict[str, Any]] = []

    def log(
        self,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
        raw_text: str = "",
        tags: Optional[List[str]] = None,
    ) -> RoomLogEntry:
        entry = RoomLogEntry(
            entry_id=str(uuid.uuid4())[:12],
            room_id=self.room_id,
            event=event,
            payload=payload or {},
            raw_text=raw_text,
            tags=list(tags or []) + ["room_log"],
        )
        row = entry.to_dict()
        with self.path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
        self.cache.append(row)
        if len(self.cache) > 500:
            self.cache = self.cache[-500:]
        # twin — NEVER filtered
        if self.twin_write:
            try:
                self.twin_write(
                    f"room_{self.room_id}",
                    row,
                    raw_text=raw_text or event,
                    original_filtered=False,
                    original_kept=True,
                    tags=["room_log", "twin_never_filtered", self.room_id],
                )
            except Exception:
                pass
        return entry

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        if self.cache:
            return self.cache[-n:]
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()[-n:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out


class AllRoomsLogger:
    """Logs for every studio room + dynamic rooms."""

    def __init__(self, user_id: str, twin_memory=None):
        self.user_id = user_id
        self.twin_memory = twin_memory
        self.books: Dict[str, RoomLogBook] = {}
        for rid in list(STUDIO_ROOMS.keys()) + list(_all_rooms().keys()):
            self._book(rid)

    def _twin_write(self, surface, payload, **kw):
        if self.twin_memory is None:
            return
        return self.twin_memory.twin_write(surface, payload, **kw)

    def _book(self, room_id: str) -> RoomLogBook:
        if room_id not in self.books:
            self.books[room_id] = RoomLogBook(room_id, self.user_id, twin_write=self._twin_write)
        return self.books[room_id]

    def log(self, room_id: str, event: str, payload: Optional[dict] = None, raw_text: str = "", tags=None):
        return self._book(room_id).log(event, payload, raw_text, tags)

    def log_all(self, event: str, payload: Optional[dict] = None, raw_text: str = ""):
        """Broadcast a system event into every room log + twins."""
        out = []
        for rid in list(self.books.keys()):
            out.append(self.log(rid, event, payload, raw_text, tags=["broadcast"]).to_dict())
        return out

    def tail(self, room_id: str, n: int = 30) -> List[Dict[str, Any]]:
        return self._book(room_id).tail(n)

    def harvest(self, n_per_room: int = 20) -> List[Dict[str, Any]]:
        rows = []
        for rid, book in self.books.items():
            rows.extend(book.tail(n_per_room))
        return rows

    def status(self) -> Dict[str, Any]:
        return {
            "rooms": list(self.books.keys()),
            "counts": {rid: len(b.cache) for rid, b in self.books.items()},
        }
