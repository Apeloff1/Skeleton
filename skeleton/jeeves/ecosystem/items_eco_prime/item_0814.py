"""Item eco_prime 0814.
"""
from __future__ import annotations

ID = "item_eco_prime_0814"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 814, "tier": 814 % 5}

def apply(context: str = "") -> dict:
    if not context and 814 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
