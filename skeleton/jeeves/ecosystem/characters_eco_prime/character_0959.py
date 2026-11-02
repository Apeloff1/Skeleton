"""Character eco_prime 0959.
"""
from __future__ import annotations

ID = "character_eco_prime_0959"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 959, "tier": 959 % 5}

def apply(context: str = "") -> dict:
    if not context and 959 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
