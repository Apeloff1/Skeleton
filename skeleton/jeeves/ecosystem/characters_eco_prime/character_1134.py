"""Character eco_prime 1134.
"""
from __future__ import annotations

ID = "character_eco_prime_1134"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1134, "tier": 1134 % 5}

def apply(context: str = "") -> dict:
    if not context and 1134 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
