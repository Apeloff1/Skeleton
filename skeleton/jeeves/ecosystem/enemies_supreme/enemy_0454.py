"""Enemy supreme 0454.
"""
from __future__ import annotations

ID = "enemy_supreme_0454"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 454, "tier": 454 % 5}

def apply(context: str = "") -> dict:
    if not context and 454 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
