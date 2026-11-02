"""Enemy eco_apex 0879.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0879"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 879, "tier": 879 % 5}

def apply(context: str = "") -> dict:
    if not context and 879 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
