"""Quest ultra 0012.
"""
from __future__ import annotations

ID = "quest_ultra_0012"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (12 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
