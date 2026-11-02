"""Quest eco_supreme 0604.
"""
from __future__ import annotations

ID = "quest_eco_supreme_0604"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (604 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
