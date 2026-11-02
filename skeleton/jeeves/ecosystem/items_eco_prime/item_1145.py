"""Item eco_prime 1145.
"""
from __future__ import annotations

ID = "item_eco_prime_1145"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1145, "tier": 1145 % 5}

def apply(context: str = "") -> dict:
    if not context and 1145 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
