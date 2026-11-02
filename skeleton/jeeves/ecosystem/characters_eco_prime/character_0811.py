"""Character eco_prime 0811.
"""
from __future__ import annotations

ID = "character_eco_prime_0811"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 811, "tier": 811 % 5}

def apply(context: str = "") -> dict:
    if not context and 811 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
