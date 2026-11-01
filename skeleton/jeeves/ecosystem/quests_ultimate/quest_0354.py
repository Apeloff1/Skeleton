"""Quest ultimate 0354.
"""
from __future__ import annotations

ID = "quest_ultimate_0354"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (354 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
