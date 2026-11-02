"""Character eco_prime 1177.
"""
from __future__ import annotations

ID = "character_eco_prime_1177"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1177, "tier": 1177 % 5}

def apply(context: str = "") -> dict:
    if not context and 1177 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
