"""Enemy supreme 0614.
"""
from __future__ import annotations

ID = "enemy_supreme_0614"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 614, "tier": 614 % 5}

def apply(context: str = "") -> dict:
    if not context and 614 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
