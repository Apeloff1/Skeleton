"""Character eco_prime 0645.
"""
from __future__ import annotations

ID = "character_eco_prime_0645"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 645, "tier": 645 % 5}

def apply(context: str = "") -> dict:
    if not context and 645 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
