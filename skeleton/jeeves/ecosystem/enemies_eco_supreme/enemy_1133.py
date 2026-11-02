"""Enemy eco_supreme 1133.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1133"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1133, "tier": 1133 % 5}

def apply(context: str = "") -> dict:
    if not context and 1133 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
