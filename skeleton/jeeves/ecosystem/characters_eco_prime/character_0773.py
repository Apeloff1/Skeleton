"""Character eco_prime 0773.
"""
from __future__ import annotations

ID = "character_eco_prime_0773"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 773, "tier": 773 % 5}

def apply(context: str = "") -> dict:
    if not context and 773 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
