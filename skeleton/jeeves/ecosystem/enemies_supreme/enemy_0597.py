"""Enemy supreme 0597.
"""
from __future__ import annotations

ID = "enemy_supreme_0597"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 597, "tier": 597 % 5}

def apply(context: str = "") -> dict:
    if not context and 597 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
