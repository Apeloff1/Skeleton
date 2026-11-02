"""Item eco_prime 0662.
"""
from __future__ import annotations

ID = "item_eco_prime_0662"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 662, "tier": 662 % 5}

def apply(context: str = "") -> dict:
    if not context and 662 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
