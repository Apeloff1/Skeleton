"""Objective marker. Points to next quest room."""
from typing import Any, Dict
class ObjectiveMarker:
    def mark(self, room: int, kind: str = "quest") -> Dict[str, Any]:
        return {"room": room, "kind": kind, "active": True}
