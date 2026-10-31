"""Quest max 0216.
"""
from __future__ import annotations

ID = "quest_max_0216"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (216 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
