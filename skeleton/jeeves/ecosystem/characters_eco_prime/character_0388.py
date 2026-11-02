"""Character eco_prime 0388.
"""
from __future__ import annotations

ID = "character_eco_prime_0388"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 388, "tier": 388 % 5}

def apply(context: str = "") -> dict:
    if not context and 388 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
