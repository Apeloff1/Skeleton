"""Optional JSONL persistence for OmniFabric snapshots.

Hex-friendly file journal for demos and single-node durability without
Mongo. Not a replacement for the outbox — it snapshots sealed history.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterator

from skeleton.kernel.omnifabric.events import FabricEvent, event_from_mapping, event_to_mapping
from skeleton.kernel.omnifabric.verify import verify_events


class JsonlEventLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self.path.touch()

    def append(self, ev: FabricEvent) -> None:
        line = json.dumps(event_to_mapping(ev), separators=(",", ":"), sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def append_many(self, events: list[FabricEvent]) -> int:
        n = 0
        for ev in events:
            self.append(ev)
            n += 1
        return n

    def iter_events(self) -> Iterator[FabricEvent]:
        with self._lock:
            text = self.path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            yield event_from_mapping(json.loads(line))

    def load_all(self) -> list[FabricEvent]:
        return list(self.iter_events())

    def verify(self) -> dict[str, Any]:
        events = self.load_all()
        report = verify_events(events, require_genesis=bool(events))
        return report.to_dict()

    def stats(self) -> dict[str, Any]:
        events = self.load_all()
        return {
            "path": str(self.path),
            "events": len(events),
            "bytes": self.path.stat().st_size if self.path.exists() else 0,
            "head_seq": events[-1].seq if events else 0,
            "head_hash": events[-1].hash if events else "genesis",
        }
