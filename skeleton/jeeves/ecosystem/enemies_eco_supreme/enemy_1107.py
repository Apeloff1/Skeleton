"""Enemy eco_supreme 1107.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1107"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1107, "tier": 1107 % 5}

def apply(context: str = "") -> dict:
    if not context and 1107 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
