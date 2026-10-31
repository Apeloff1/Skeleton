"""Enemy max 0300.
"""
from __future__ import annotations

ID = "enemy_max_0300"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 300, "tier": 300 % 5}

def apply(context: str = "") -> dict:
    if not context and 300 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
