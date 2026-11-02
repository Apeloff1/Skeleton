"""Enemy eco_supreme 0858.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0858"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 858, "tier": 858 % 5}

def apply(context: str = "") -> dict:
    if not context and 858 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
