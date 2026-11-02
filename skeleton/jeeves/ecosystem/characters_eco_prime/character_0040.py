"""Character eco_prime 0040.
"""
from __future__ import annotations

ID = "character_eco_prime_0040"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 40, "tier": 40 % 5}

def apply(context: str = "") -> dict:
    if not context and 40 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
