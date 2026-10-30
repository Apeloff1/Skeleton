"""Enemy mega 0162.
"""
from __future__ import annotations

ID = "enemy_mega_0162"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 162, "tier": 162 % 5}

def apply(context: str = "") -> dict:
    if not context and 162 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
