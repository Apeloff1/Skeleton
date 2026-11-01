"""Enemy supreme 0600.
"""
from __future__ import annotations

ID = "enemy_supreme_0600"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 600, "tier": 600 % 5}

def apply(context: str = "") -> dict:
    if not context and 600 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
