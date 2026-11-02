"""Character eco_prime 0171.
"""
from __future__ import annotations

ID = "character_eco_prime_0171"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 171, "tier": 171 % 5}

def apply(context: str = "") -> dict:
    if not context and 171 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
