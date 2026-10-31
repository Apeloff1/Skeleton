"""Title max 0103.
"""
from __future__ import annotations

ID = "title_max_0103"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 103}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
