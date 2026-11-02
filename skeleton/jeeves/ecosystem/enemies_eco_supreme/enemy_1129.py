"""Enemy eco_supreme 1129.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1129"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1129, "tier": 1129 % 5}

def apply(context: str = "") -> dict:
    if not context and 1129 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
