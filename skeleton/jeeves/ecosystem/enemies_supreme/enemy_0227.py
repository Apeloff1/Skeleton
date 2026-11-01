"""Enemy supreme 0227.
"""
from __future__ import annotations

ID = "enemy_supreme_0227"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 227, "tier": 227 % 5}

def apply(context: str = "") -> dict:
    if not context and 227 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
