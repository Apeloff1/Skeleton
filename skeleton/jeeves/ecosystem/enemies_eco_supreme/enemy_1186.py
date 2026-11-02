"""Enemy eco_supreme 1186.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1186"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1186, "tier": 1186 % 5}

def apply(context: str = "") -> dict:
    if not context and 1186 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
