"""Quest ultimate 0370.
"""
from __future__ import annotations

ID = "quest_ultimate_0370"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (370 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
