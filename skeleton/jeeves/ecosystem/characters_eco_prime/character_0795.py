"""Character eco_prime 0795.
"""
from __future__ import annotations

ID = "character_eco_prime_0795"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 795, "tier": 795 % 5}

def apply(context: str = "") -> dict:
    if not context and 795 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
