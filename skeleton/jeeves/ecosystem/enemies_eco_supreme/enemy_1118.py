"""Enemy eco_supreme 1118.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1118"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1118, "tier": 1118 % 5}

def apply(context: str = "") -> dict:
    if not context and 1118 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
