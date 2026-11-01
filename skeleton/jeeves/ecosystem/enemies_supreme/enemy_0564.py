"""Enemy supreme 0564.
"""
from __future__ import annotations

ID = "enemy_supreme_0564"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 564, "tier": 564 % 5}

def apply(context: str = "") -> dict:
    if not context and 564 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
