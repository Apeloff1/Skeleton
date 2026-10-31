"""Character peak 0448.
"""
from __future__ import annotations

ID = "character_peak_0448"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 448, "tier": 448 % 5}

def apply(context: str = "") -> dict:
    if not context and 448 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
