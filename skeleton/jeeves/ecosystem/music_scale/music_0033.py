"""Music scale 0033.
"""
from __future__ import annotations

ID = "music_scale_0033"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 33}

def activate(context: str = "") -> dict:
    if not context and 33 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
