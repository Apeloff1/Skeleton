"""Item eco_prime 1172.
"""
from __future__ import annotations

ID = "item_eco_prime_1172"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1172, "tier": 1172 % 5}

def apply(context: str = "") -> dict:
    if not context and 1172 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
