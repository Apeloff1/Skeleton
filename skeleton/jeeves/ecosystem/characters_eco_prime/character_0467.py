"""Character eco_prime 0467.
"""
from __future__ import annotations

ID = "character_eco_prime_0467"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 467, "tier": 467 % 5}

def apply(context: str = "") -> dict:
    if not context and 467 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
