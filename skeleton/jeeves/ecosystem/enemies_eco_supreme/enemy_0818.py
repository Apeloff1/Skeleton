"""Enemy eco_supreme 0818.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0818"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 818, "tier": 818 % 5}

def apply(context: str = "") -> dict:
    if not context and 818 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
