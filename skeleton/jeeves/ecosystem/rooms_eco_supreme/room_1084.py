"""Room eco_supreme 1084.
"""
from __future__ import annotations

ID = "room_eco_supreme_1084"

def describe() -> dict:
    return {"id": ID, "kind": "room", "power": 5 + (1084 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
