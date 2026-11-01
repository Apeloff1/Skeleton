"""Enemy supreme 0628.
"""
from __future__ import annotations

ID = "enemy_supreme_0628"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 628, "tier": 628 % 5}

def apply(context: str = "") -> dict:
    if not context and 628 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
