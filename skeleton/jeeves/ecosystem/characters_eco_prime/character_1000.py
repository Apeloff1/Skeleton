"""Character eco_prime 1000.
"""
from __future__ import annotations

ID = "character_eco_prime_1000"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1000, "tier": 1000 % 5}

def apply(context: str = "") -> dict:
    if not context and 1000 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
