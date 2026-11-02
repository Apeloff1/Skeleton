"""Character eco_prime 0978.
"""
from __future__ import annotations

ID = "character_eco_prime_0978"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 978, "tier": 978 % 5}

def apply(context: str = "") -> dict:
    if not context and 978 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
