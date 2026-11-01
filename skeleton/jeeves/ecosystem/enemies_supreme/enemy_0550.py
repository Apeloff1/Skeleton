"""Enemy supreme 0550.
"""
from __future__ import annotations

ID = "enemy_supreme_0550"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 550, "tier": 550 % 5}

def apply(context: str = "") -> dict:
    if not context and 550 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
