"""Enemy supreme 0028.
"""
from __future__ import annotations

ID = "enemy_supreme_0028"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 28, "tier": 28 % 5}

def apply(context: str = "") -> dict:
    if not context and 28 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
