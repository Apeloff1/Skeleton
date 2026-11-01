"""Title ultra_max 0207.
"""
from __future__ import annotations

ID = "title_ultra_max_0207"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 207}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
