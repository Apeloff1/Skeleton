"""Enemy eco_supreme 0734.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0734"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 734, "tier": 734 % 5}

def apply(context: str = "") -> dict:
    if not context and 734 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
