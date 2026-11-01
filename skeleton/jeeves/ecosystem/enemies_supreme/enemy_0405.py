"""Enemy supreme 0405.
"""
from __future__ import annotations

ID = "enemy_supreme_0405"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 405, "tier": 405 % 5}

def apply(context: str = "") -> dict:
    if not context and 405 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
