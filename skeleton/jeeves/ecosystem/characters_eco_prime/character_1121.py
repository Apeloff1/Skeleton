"""Character eco_prime 1121.
"""
from __future__ import annotations

ID = "character_eco_prime_1121"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1121, "tier": 1121 % 5}

def apply(context: str = "") -> dict:
    if not context and 1121 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
