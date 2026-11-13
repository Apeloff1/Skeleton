"""Bestiary. Tracks encountered enemy types."""
from typing import Any, Dict, Set
class Bestiary:
    def __init__(self):
        self.seen: Set[str] = set()
    def encounter(self, kind: str) -> None:
        self.seen.add(kind)
    def count(self) -> int:
        return len(self.seen)
