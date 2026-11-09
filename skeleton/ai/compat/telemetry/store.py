"""Event store. Appends are kind+seq only. No prose payload."""

from __future__ import annotations


class EventStore:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def append(self, kind: str) -> dict:
        rec = {"seq": len(self.events) + 1, "kind": kind, "stored_prose": 0}
        self.events.append(rec)
        return rec
