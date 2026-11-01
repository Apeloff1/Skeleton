"""Title ultra_max 0226.
"""
from __future__ import annotations

ID = "title_ultra_max_0226"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 226}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
