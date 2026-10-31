"""Changelog. Short version history for the studio."""
from typing import Any, Dict, List
class Changelog:
    def __init__(self):
        self.log: List[Dict[str, str]] = []
    def add(self, version: str, note: str) -> None:
        self.log.append({"version": version, "note": note})
    def recent(self, n: int = 5) -> List[Dict[str, str]]:
        return self.log[-n:]
