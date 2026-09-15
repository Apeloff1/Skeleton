from __future__ import annotations
"""
Masterlog — single spine for every log and audit trail.
Everything that happens in rooms, VOX, security, training, DNA, studio → here.
"""

import json
import os
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MasterEntry:
    master_id: str
    source: str          # room_id | system | security | vox | dna | studio | training | twin
    category: str        # log | audit | threat | vote | train | backup
    event: str
    payload: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


class Masterlog:
    """
    Append-only master spine + optional twin mirror + marathon store hook.
    """

    def __init__(self, user_id: str = "default", twin_write=None, store_event=None):
        self.user_id = user_id
        self.twin_write = twin_write
        self.store_event = store_event
        self._lock = threading.RLock()
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.path = base / "masterlog" / user_id / "master.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cache: Deque[Dict[str, Any]] = deque(maxlen=5000)
        self.count = 0

    def write(
        self,
        source: str,
        category: str,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
        raw_text: str = "",
        tags: Optional[List[str]] = None,
    ) -> MasterEntry:
        entry = MasterEntry(
            master_id=str(uuid.uuid4())[:14],
            source=source,
            category=category,
            event=event,
            payload=payload or {},
            raw_text=raw_text,
            tags=list(tags or []) + ["masterlog"],
        )
        row = entry.to_dict()
        with self._lock:
            with self.path.open("a") as f:
                f.write(json.dumps(row, default=str) + "\n")
            self.cache.append(row)
            self.count += 1
        if self.twin_write:
            try:
                self.twin_write(
                    "masterlog",
                    row,
                    raw_text=raw_text or event,
                    original_filtered=False,
                    original_kept=True,
                    tags=["masterlog", "twin_never_filtered"],
                )
            except Exception:
                pass
        if self.store_event:
            try:
                self.store_event("masterlog", event, row)
            except Exception:
                pass
        return entry

    def tail(self, n: int = 100, *, source: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = list(self.cache)
        if source:
            rows = [r for r in rows if r.get("source") == source]
        if category:
            rows = [r for r in rows if r.get("category") == category]
        return rows[-n:]

    def status(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "path": str(self.path),
            "count": self.count,
            "cache": len(self.cache),
        }
