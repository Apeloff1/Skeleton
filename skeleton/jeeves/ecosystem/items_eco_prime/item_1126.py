"""Item eco_prime 1126.
"""
from __future__ import annotations

ID = "item_eco_prime_1126"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1126, "tier": 1126 % 5}

def apply(context: str = "") -> dict:
    if not context and 1126 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
