"""Quest ultra_max 0393.
"""
from __future__ import annotations

ID = "quest_ultra_max_0393"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (393 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
