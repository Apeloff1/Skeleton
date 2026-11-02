"""Enemy eco_supreme 0578.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0578"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 578, "tier": 578 % 5}

def apply(context: str = "") -> dict:
    if not context and 578 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
