"""Save slot manager.
Multiple named slots for pipeline state, with load and list.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

class SaveSlotManager:
    def __init__(self):
        self.slots: Dict[str, Dict[str, Any]] = {}
    def save(self, name: str, state: Dict[str, Any]) -> bool:
        self.slots[name] = dict(state)
        return True
    def load(self, name: str) -> Optional[Dict[str, Any]]:
        return self.slots.get(name)
    def list_slots(self) -> List[str]:
        return list(self.slots.keys())
    def delete(self, name: str) -> bool:
        if name in self.slots:
            del self.slots[name]
            return True
        return False
