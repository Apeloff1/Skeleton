from __future__ import annotations
"""
Twin logs: originals filter; twins keep everything for reference.
Created synergistically on every write path; queried on demand.
"""

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TwinEntry:
    twin_id: str
    stream: str  # transcript | schedule | progress | journal | neuro | math | system
    original_filtered: bool
    original_kept: bool
    payload: Dict[str, Any]
    raw_text: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class TwinLogBook:
    """
    Append-only complete account. Never filters.
    """

    def __init__(self, user_id: str, stream: str = "general"):
        self.user_id = user_id
        self.stream = stream
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.root = base / "twin_logs" / user_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / f"{stream}.jsonl"
        self._cache: List[Dict[str, Any]] = []
        self._load_tail(500)

    def _load_tail(self, n: int):
        if not self.path.exists():
            return
        lines = self.path.read_text().splitlines()
        for line in lines[-n:]:
            try:
                self._cache.append(json.loads(line))
            except Exception:
                pass

    def append(
        self,
        payload: Dict[str, Any],
        *,
        raw_text: str = "",
        original_filtered: bool = False,
        original_kept: bool = True,
        tags: Optional[List[str]] = None,
    ) -> TwinEntry:
        entry = TwinEntry(
            twin_id=str(uuid.uuid4())[:12],
            stream=self.stream,
            original_filtered=original_filtered,
            original_kept=original_kept,
            payload=payload,
            raw_text=raw_text,
            tags=tags or [],
        )
        row = entry.to_dict()
        with self.path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
        self._cache.append(row)
        if len(self._cache) > 2000:
            self._cache = self._cache[-2000:]
        return entry

    def query(
        self,
        *,
        contains: Optional[str] = None,
        tag: Optional[str] = None,
        only_filtered_originals: bool = False,
        n: int = 50,
    ) -> List[Dict[str, Any]]:
        rows = list(self._cache)
        # also scan file if needed for deep query
        if self.path.exists() and (contains or only_filtered_originals or tag):
            rows = []
            with self.path.open() as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
        out = []
        for r in rows:
            if only_filtered_originals and not r.get("original_filtered"):
                continue
            if tag and tag not in (r.get("tags") or []):
                continue
            if contains:
                blob = (r.get("raw_text") or "") + json.dumps(r.get("payload") or {})
                if contains.lower() not in blob.lower():
                    continue
            out.append(r)
        return out[-n:]

    def stats(self) -> Dict[str, Any]:
        total = 0
        filtered = 0
        if self.path.exists():
            with self.path.open() as f:
                for line in f:
                    total += 1
                    try:
                        if json.loads(line).get("original_filtered"):
                            filtered += 1
                    except Exception:
                        pass
        return {
            "stream": self.stream,
            "total_twin_entries": total,
            "originals_filtered_count": filtered,
            "path": str(self.path),
        }


class TwinHub:
    """All twin streams for a user."""

    STREAMS = (
        "transcript",
        "schedule",
        "progress",
        "journal",
        "neuro",
        "math",
        "system",
        "general",
    )

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.books = {s: TwinLogBook(user_id, s) for s in self.STREAMS}

    def mirror(
        self,
        stream: str,
        payload: Dict[str, Any],
        *,
        raw_text: str = "",
        original_filtered: bool = False,
        original_kept: bool = True,
        tags: Optional[List[str]] = None,
    ) -> TwinEntry:
        book = self.books.get(stream) or self.books["general"]
        return book.append(
            payload,
            raw_text=raw_text,
            original_filtered=original_filtered,
            original_kept=original_kept,
            tags=tags,
        )

    def query(self, stream: str = "general", **kwargs) -> List[Dict[str, Any]]:
        book = self.books.get(stream) or self.books["general"]
        return book.query(**kwargs)

    def query_all(self, contains: str, n: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        return {s: self.books[s].query(contains=contains, n=n) for s in self.STREAMS}

    def overview(self) -> Dict[str, Any]:
        return {s: self.books[s].stats() for s in self.STREAMS}
