"""Title ultra_max 0180.
"""
from __future__ import annotations

ID = "title_ultra_max_0180"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 180}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
