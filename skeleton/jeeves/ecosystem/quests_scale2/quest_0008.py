"""Quest scale2 0008.
"""
from __future__ import annotations

ID = "quest_scale2_0008"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 8}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
