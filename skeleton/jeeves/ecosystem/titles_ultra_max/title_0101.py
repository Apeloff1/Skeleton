"""Title ultra_max 0101.
"""
from __future__ import annotations

ID = "title_ultra_max_0101"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 101}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
