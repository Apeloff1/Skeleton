"""Character peak 0440.
"""
from __future__ import annotations

ID = "character_peak_0440"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 440, "tier": 440 % 5}

def apply(context: str = "") -> dict:
    if not context and 440 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
