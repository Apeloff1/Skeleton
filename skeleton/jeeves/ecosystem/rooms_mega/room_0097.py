"""Room mega 0097.
"""
from __future__ import annotations

ID = "room_mega_0097"

def describe() -> dict:
    return {"id": ID, "kind": "room", "power": 5 + (97 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
