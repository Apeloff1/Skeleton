"""Quest ultra 0065.
"""
from __future__ import annotations

ID = "quest_ultra_0065"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (65 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
