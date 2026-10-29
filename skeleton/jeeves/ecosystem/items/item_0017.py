"""Item 0017.
"""
from __future__ import annotations

ITEM = "item_0017"
RARITY = ["common", "rare", "epic"][17 % 3]

def stats() -> dict:
    return {"id": ITEM, "rarity": RARITY, "value": 10 + 17, "stack": 1 if RARITY == "epic" else 99}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "item": ITEM, "target": target, "effect": "apply"}
