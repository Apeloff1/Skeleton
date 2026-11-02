"""Character eco_prime 0802.
"""
from __future__ import annotations

ID = "character_eco_prime_0802"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 802, "tier": 802 % 5}

def apply(context: str = "") -> dict:
    if not context and 802 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
