"""Item eco_prime 0966.
"""
from __future__ import annotations

ID = "item_eco_prime_0966"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 966, "tier": 966 % 5}

def apply(context: str = "") -> dict:
    if not context and 966 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
