"""Title max 0001.
"""
from __future__ import annotations

ID = "title_max_0001"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 1}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
