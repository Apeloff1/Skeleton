"""Lore entry. Pointer-only text key for localization."""
from typing import Any, Dict
class LoreEntry:
    def __init__(self, key: str):
        self.key = key
        self.unlocked = False
    def unlock(self) -> str:
        self.unlocked = True
        return self.key
