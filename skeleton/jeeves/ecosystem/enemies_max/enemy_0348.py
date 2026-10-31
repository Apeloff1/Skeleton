"""Enemy max 0348.
"""
from __future__ import annotations

ID = "enemy_max_0348"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 348, "tier": 348 % 5}

def apply(context: str = "") -> dict:
    if not context and 348 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
