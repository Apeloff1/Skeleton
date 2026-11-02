"""Enemy eco_supreme 0810.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0810"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 810, "tier": 810 % 5}

def apply(context: str = "") -> dict:
    if not context and 810 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
