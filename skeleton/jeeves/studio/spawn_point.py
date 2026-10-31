"""Spawn point. Player or enemy start locations."""
from typing import Any, Dict
class SpawnPoint:
    def __init__(self, pos: tuple, kind: str = "player"):
        self.pos = pos
        self.kind = kind
    def location(self) -> tuple:
        return self.pos
