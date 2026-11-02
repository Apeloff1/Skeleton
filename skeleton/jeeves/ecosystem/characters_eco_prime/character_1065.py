"""Character eco_prime 1065.
"""
from __future__ import annotations

ID = "character_eco_prime_1065"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1065, "tier": 1065 % 5}

def apply(context: str = "") -> dict:
    if not context and 1065 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
