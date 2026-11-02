"""Character eco_prime 1196.
"""
from __future__ import annotations

ID = "character_eco_prime_1196"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1196, "tier": 1196 % 5}

def apply(context: str = "") -> dict:
    if not context and 1196 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
