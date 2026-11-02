"""Character eco_prime 1002.
"""
from __future__ import annotations

ID = "character_eco_prime_1002"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1002, "tier": 1002 % 5}

def apply(context: str = "") -> dict:
    if not context and 1002 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
