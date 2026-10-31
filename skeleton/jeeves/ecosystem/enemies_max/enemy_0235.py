"""Enemy max 0235.
"""
from __future__ import annotations

ID = "enemy_max_0235"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 235, "tier": 235 % 5}

def apply(context: str = "") -> dict:
    if not context and 235 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
