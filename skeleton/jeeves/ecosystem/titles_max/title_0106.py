"""Title max 0106.
"""
from __future__ import annotations

ID = "title_max_0106"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 106}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
