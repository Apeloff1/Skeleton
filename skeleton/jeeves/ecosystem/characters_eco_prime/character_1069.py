"""Character eco_prime 1069.
"""
from __future__ import annotations

ID = "character_eco_prime_1069"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1069, "tier": 1069 % 5}

def apply(context: str = "") -> dict:
    if not context and 1069 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
