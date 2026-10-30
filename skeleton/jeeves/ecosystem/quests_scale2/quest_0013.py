"""Quest scale2 0013.
"""
from __future__ import annotations

ID = "quest_scale2_0013"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 13}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
