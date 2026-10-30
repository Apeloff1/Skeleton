"""Quest mega 0036.
"""
from __future__ import annotations

ID = "quest_mega_0036"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (36 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
