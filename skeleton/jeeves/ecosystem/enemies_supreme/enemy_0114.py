"""Enemy supreme 0114.
"""
from __future__ import annotations

ID = "enemy_supreme_0114"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 114, "tier": 114 % 5}

def apply(context: str = "") -> dict:
    if not context and 114 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
