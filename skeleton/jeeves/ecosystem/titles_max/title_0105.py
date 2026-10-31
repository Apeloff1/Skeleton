"""Title max 0105.
"""
from __future__ import annotations

ID = "title_max_0105"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 105}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
