"""Item eco_prime 0692.
"""
from __future__ import annotations

ID = "item_eco_prime_0692"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 692, "tier": 692 % 5}

def apply(context: str = "") -> dict:
    if not context and 692 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
