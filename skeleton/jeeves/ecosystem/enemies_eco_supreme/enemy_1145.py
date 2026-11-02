"""Enemy eco_supreme 1145.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_1145"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1145, "tier": 1145 % 5}

def apply(context: str = "") -> dict:
    if not context and 1145 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
