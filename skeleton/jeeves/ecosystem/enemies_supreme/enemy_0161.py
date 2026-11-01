"""Enemy supreme 0161.
"""
from __future__ import annotations

ID = "enemy_supreme_0161"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 161, "tier": 161 % 5}

def apply(context: str = "") -> dict:
    if not context and 161 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
