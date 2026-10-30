"""Effect scale 0044.
"""
from __future__ import annotations

ID = "effect_scale_0044"

def describe() -> dict:
    return {"id": ID, "kind": "effect", "power": 5 + (44 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
