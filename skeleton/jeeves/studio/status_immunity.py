"""Status immunity. Blocks specific debuffs."""
from typing import Any, Dict, Set
class StatusImmunity:
    def __init__(self):
        self.immune: Set[str] = set()
    def grant(self, status: str) -> None:
        self.immune.add(status)
    def blocks(self, status: str) -> bool:
        return status in self.immune
