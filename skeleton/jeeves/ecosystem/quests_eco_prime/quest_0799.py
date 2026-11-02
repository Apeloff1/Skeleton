"""Quest eco_prime 0799.
"""
from __future__ import annotations

ID = "quest_eco_prime_0799"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "power": 5 + (799 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
