"""Enemy mega 0164.
"""
from __future__ import annotations

ID = "enemy_mega_0164"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 164, "tier": 164 % 5}

def apply(context: str = "") -> dict:
    if not context and 164 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
