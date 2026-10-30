"""Enemy mega 0113.
"""
from __future__ import annotations

ID = "enemy_mega_0113"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 113, "tier": 113 % 5}

def apply(context: str = "") -> dict:
    if not context and 113 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
