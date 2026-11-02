"""Character eco_prime 0589.
"""
from __future__ import annotations

ID = "character_eco_prime_0589"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 589, "tier": 589 % 5}

def apply(context: str = "") -> dict:
    if not context and 589 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
