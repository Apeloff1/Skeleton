"""Enemy max 0200.
"""
from __future__ import annotations

ID = "enemy_max_0200"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 200, "tier": 200 % 5}

def apply(context: str = "") -> dict:
    if not context and 200 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
