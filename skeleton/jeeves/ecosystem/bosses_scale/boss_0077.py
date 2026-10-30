"""Boss scale 0077.
"""
from __future__ import annotations

ID = "boss_scale_0077"

def describe() -> dict:
    return {"id": ID, "kind": "boss", "index": 77}

def activate(context: str = "") -> dict:
    if not context and 77 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
