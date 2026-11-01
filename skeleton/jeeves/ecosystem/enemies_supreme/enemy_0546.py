"""Enemy supreme 0546.
"""
from __future__ import annotations

ID = "enemy_supreme_0546"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 546, "tier": 546 % 5}

def apply(context: str = "") -> dict:
    if not context and 546 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
