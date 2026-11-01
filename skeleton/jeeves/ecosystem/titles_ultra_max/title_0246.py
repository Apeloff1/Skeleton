"""Title ultra_max 0246.
"""
from __future__ import annotations

ID = "title_ultra_max_0246"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 246}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
