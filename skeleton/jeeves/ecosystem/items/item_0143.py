"""Item 0143.
"""
from __future__ import annotations

ITEM = "item_0143"
RARITY = ["common", "rare", "epic"][143 % 3]

def stats() -> dict:
    return {"id": ITEM, "rarity": RARITY, "value": 10 + 143, "stack": 1 if RARITY == "epic" else 99}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "item": ITEM, "target": target, "effect": "apply"}
