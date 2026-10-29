"""Tutorial system.
Step-by-step prompts for first-run and optical feedback.
"""
from __future__ import annotations
from typing import Any, Dict, List

STEPS = [
    {"id": "move", "prompt": "Move with directional input.", "done": False},
    {"id": "clear_pack", "prompt": "Clear a salvage pack.", "done": False},
    {"id": "spend", "prompt": "Spend salvage on an upgrade.", "done": False},
    {"id": "optical", "prompt": "Raise optical diversity above 0.9.", "done": False},
    {"id": "boss", "prompt": "Engage the multi-phase boss.", "done": False},
]

class TutorialSystem:
    def __init__(self):
        self.steps = [dict(s) for s in STEPS]
        self.current = 0
    def advance(self, event: str) -> Dict[str, Any]:
        if self.current < len(self.steps):
            step = self.steps[self.current]
            if event == step["id"] or event == "any":
                step["done"] = True
                self.current += 1
        return {"current": self.current, "completed": self.current >= len(self.steps), "next": self.steps[self.current]["prompt"] if self.current < len(self.steps) else "done"}
    def status(self) -> Dict[str, Any]:
        return {"current": self.current, "total": len(self.steps), "done": sum(1 for s in self.steps if s["done"])}
