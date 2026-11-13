"""Input recorder.
Captures action sequences for replay or critique.
"""
from __future__ import annotations
from typing import Any, Dict, List

class InputRecorder:
    def __init__(self):
        self.actions: List[Dict[str, Any]] = []
    def record(self, action: str, t: float = 0.0) -> None:
        self.actions.append({"action": action, "t": t})
    def length(self) -> int:
        return len(self.actions)
    def export(self) -> Dict[str, Any]:
        return {"actions": self.actions[-100:], "count": len(self.actions), "schema": "skeleton.input.v1"}
