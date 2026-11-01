"""Title supreme 0278.
"""
from __future__ import annotations

ID = "title_supreme_0278"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 278}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
