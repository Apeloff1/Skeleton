"""Enemy supreme 0680.
"""
from __future__ import annotations

ID = "enemy_supreme_0680"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 680, "tier": 680 % 5}

def apply(context: str = "") -> dict:
    if not context and 680 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
