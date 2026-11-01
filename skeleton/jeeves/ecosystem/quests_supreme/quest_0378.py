"""Quest supreme 0378.
"""
from __future__ import annotations

ID = "quest_supreme_0378"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (378 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
