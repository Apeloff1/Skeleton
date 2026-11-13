"""Puzzle lock. Optical or sequence based unlock."""
from typing import Any, Dict, List
class PuzzleLock:
    def __init__(self, sequence: List[int]):
        self.sequence = sequence
        self.progress = []
    def input(self, n: int) -> bool:
        self.progress.append(n)
        if self.progress == self.sequence: return True
        if len(self.progress) >= len(self.sequence): self.progress = []
        return False
