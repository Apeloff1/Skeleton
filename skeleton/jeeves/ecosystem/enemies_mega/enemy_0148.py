"""Enemy mega 0148.
"""
from __future__ import annotations

ID = "enemy_mega_0148"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 148, "tier": 148 % 5}

def apply(context: str = "") -> dict:
    if not context and 148 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
