"""Character eco_prime 0696.
"""
from __future__ import annotations

ID = "character_eco_prime_0696"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 696, "tier": 696 % 5}

def apply(context: str = "") -> dict:
    if not context and 696 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
