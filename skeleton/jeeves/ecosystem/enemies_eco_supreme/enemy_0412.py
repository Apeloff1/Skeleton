"""Enemy eco_supreme 0412.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0412"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 412, "tier": 412 % 5}

def apply(context: str = "") -> dict:
    if not context and 412 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
