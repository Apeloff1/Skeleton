"""Quest eco_apex 0513.
"""
from __future__ import annotations

ID = "quest_eco_apex_0513"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (513 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
