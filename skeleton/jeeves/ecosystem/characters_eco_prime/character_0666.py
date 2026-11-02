"""Character eco_prime 0666.
"""
from __future__ import annotations

ID = "character_eco_prime_0666"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 666, "tier": 666 % 5}

def apply(context: str = "") -> dict:
    if not context and 666 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
