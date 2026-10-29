"""Aggro system. Enemy targeting priority."""
from typing import Any, Dict
class AggroSystem:
    def __init__(self):
        self.table: Dict[str, float] = {}
    def add(self, target: str, amount: float) -> None:
        self.table[target] = self.table.get(target, 0) + amount
    def top(self) -> str:
        return max(self.table, key=self.table.get) if self.table else ""
