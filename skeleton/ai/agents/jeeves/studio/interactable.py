"""Interactable. Doors, caches, terminals."""
from typing import Any, Dict
class Interactable:
    def __init__(self, kind: str, room: int):
        self.kind = kind
        self.room = room
        self.used = False
    def use(self) -> Dict[str, Any]:
        if self.used: return {"ok": False}
        self.used = True
        return {"ok": True, "kind": self.kind}
