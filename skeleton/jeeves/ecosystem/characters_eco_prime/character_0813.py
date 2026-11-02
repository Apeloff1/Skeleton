"""Character eco_prime 0813.
"""
from __future__ import annotations

ID = "character_eco_prime_0813"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 813, "tier": 813 % 5}

def apply(context: str = "") -> dict:
    if not context and 813 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
