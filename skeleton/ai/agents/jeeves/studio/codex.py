"""Codex. Unlocked lore and system entries."""
from typing import Any, Dict, List
class Codex:
    def __init__(self):
        self.entries: List[str] = []
    def add(self, key: str) -> None:
        if key not in self.entries: self.entries.append(key)
    def all(self) -> List[str]:
        return self.entries
