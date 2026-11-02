"""Enemy eco_apex 0754.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0754"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 754, "tier": 754 % 5}

def apply(context: str = "") -> dict:
    if not context and 754 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
