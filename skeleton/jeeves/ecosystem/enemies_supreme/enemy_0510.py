"""Enemy supreme 0510.
"""
from __future__ import annotations

ID = "enemy_supreme_0510"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 510, "tier": 510 % 5}

def apply(context: str = "") -> dict:
    if not context and 510 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
