"""Enemy supreme 0435.
"""
from __future__ import annotations

ID = "enemy_supreme_0435"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 435, "tier": 435 % 5}

def apply(context: str = "") -> dict:
    if not context and 435 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
