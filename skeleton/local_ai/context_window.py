"""
Operational Context Window. Sliding window of turns with truncation and helix-backed persistence.
Fills the context management gap.
"""
from typing import List, Dict
from .helix_persist import HelixPersist

class ContextWindow:
    def __init__(self, max_turns: int = 16):
        self.max_turns = max_turns
        self.turns: List[Dict] = []
        self.helix = HelixPersist("chronicle/context.jsonl")

    def add(self, turn: Dict) -> None:
        self.turns.append(turn)
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
        self.helix.append([turn])

    def get(self) -> List[Dict]:
        return self.turns.copy()

    def clear(self) -> None:
        self.turns.clear()
