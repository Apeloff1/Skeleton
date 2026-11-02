"""Item eco_prime 1103.
"""
from __future__ import annotations

ID = "item_eco_prime_1103"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1103, "tier": 1103 % 5}

def apply(context: str = "") -> dict:
    if not context and 1103 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
