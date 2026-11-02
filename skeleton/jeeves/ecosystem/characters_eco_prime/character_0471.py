"""Character eco_prime 0471.
"""
from __future__ import annotations

ID = "character_eco_prime_0471"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 471, "tier": 471 % 5}

def apply(context: str = "") -> dict:
    if not context and 471 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
