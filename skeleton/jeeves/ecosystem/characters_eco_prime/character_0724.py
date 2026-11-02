"""Character eco_prime 0724.
"""
from __future__ import annotations

ID = "character_eco_prime_0724"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 724, "tier": 724 % 5}

def apply(context: str = "") -> dict:
    if not context and 724 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
