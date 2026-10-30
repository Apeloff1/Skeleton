"""Quest mega 0074.
"""
from __future__ import annotations

ID = "quest_mega_0074"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (74 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
