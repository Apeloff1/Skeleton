"""Title supreme 0200.
"""
from __future__ import annotations

ID = "title_supreme_0200"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 200}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
