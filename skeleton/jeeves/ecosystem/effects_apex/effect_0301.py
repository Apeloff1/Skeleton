"""Effect apex 0301.
"""
from __future__ import annotations

ID = "effect_apex_0301"

def describe() -> dict:
    return {"id": ID, "kind": "effect", "power": 5 + (301 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
