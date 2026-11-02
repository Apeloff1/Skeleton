"""Effect eco_supreme 0628.
"""
from __future__ import annotations

ID = "effect_eco_supreme_0628"

def describe() -> dict:
    return {"id": ID, "kind": "effect", "power": 5 + (628 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
