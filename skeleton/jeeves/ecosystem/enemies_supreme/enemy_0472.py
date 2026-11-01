"""Enemy supreme 0472.
"""
from __future__ import annotations

ID = "enemy_supreme_0472"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 472, "tier": 472 % 5}

def apply(context: str = "") -> dict:
    if not context and 472 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
